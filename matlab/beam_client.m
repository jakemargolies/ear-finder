function beam_client()
% beam_client  Play beamformed audio steered to a tracked head position.
%
% Set MODE in config.m before running:
%
%   'delay'  Local delay-and-sum.  No GPU server needed.
%            Only prerequisites: netbridge running + this script.
%
%   'avdar'  AV-DAR matched-filter FIR via GPU server.
%            Prerequisites: SSH tunnel active, GPU server running, netbridge.
%
% In both modes, head position arrives via UDP loopback from netbridge
% as 12-byte little-endian float32[3] = [x, y, z] in meters (camera frame).

    run('config.m');

    % ----------------------------------------------------------------
    % Audio setup (shared by both modes)
    % ----------------------------------------------------------------
    playRec = audioPlayerRecorder( ...
        'Device', DEVICE_NAME, ...
        'BitDepth', '24-bit integer', ...
        'PlayerChannelMapping', 1:NUM_CHANNELS);
    fs_device = playRec.SampleRate;

    N     = round(CHUNK_DURATION * fs_device);
    t_vec = (0:N-1).' / fs_device;
    h     = 0.5 * sin(2*pi * TONE_FREQ * t_vec);   % mono source signal

    % ----------------------------------------------------------------
    % UDP receiver (shared by both modes)
    % ----------------------------------------------------------------
    u = udpport('LocalPort', UDP_POS_PORT);
    fprintf('beam_client [%s]: receiving head position on UDP port %d\n', ...
        MODE, UDP_POS_PORT);

    % ----------------------------------------------------------------
    % Mode-specific setup
    % ----------------------------------------------------------------
    switch MODE

        case 'delay'
            fprintf('beam_client: delay-and-sum mode (no server needed)\n\n');

            % Initial weights: centered, no delay
            w   = ones(NUM_CHANNELS, 1);
            tau = zeros(NUM_CHANNELS, 1);

        case 'avdar'
            fprintf('beam_client: connecting to AV-DAR server %s:%d ...\n', ...
                SERVER_HOST, SERVER_PORT);
            srv = tcpclient(SERVER_HOST, SERVER_PORT, 'Timeout', SERVER_TIMEOUT);
            fprintf('beam_client: connected.\n\n');

            % Default filter bank: identity (pass-through, equal on all channels)
            filters   = ones(1, NUM_CHANNELS);
            zi        = init_filter_state(filters, NUM_CHANNELS);
            seq_id    = int32(0);
            fs_server = fs_device;

        otherwise
            error('beam_client: unknown MODE "%s". Set MODE to ''delay'' or ''avdar''.', MODE);
    end

    fprintf('beam_client: audio loop running. Ctrl-C to stop.\n\n');

    rx_pos = [];

    % ----------------------------------------------------------------
    % Main loop
    % ----------------------------------------------------------------
    while true

        % --- 1. Check for new head position ---
        if u.NumBytesAvailable >= 12
            raw    = read(u, 12, 'uint8');
            floats = typecast(uint8(raw), 'single');
            rx_pos = double(floats(:)');   % row [x, y, z]
        end

        % --- 2. Update beamforming parameters when position changes ---
        if ~isempty(rx_pos)
            switch MODE

                case 'delay'
                    [w, tau] = delay_sum_weights( ...
                        rx_pos, SPEAKER_POSITIONS_M, SPEED_OF_SOUND);
                    fprintf('  pos=[%+.2f %+.2f %+.2f]  tau_ms=[%.2f %.2f %.2f %.2f]\n', ...
                        rx_pos(1), rx_pos(2), rx_pos(3), tau*1e3);
                    rx_pos = [];

                case 'avdar'
                    req = struct( ...
                        'type',        'rx_pos', ...
                        'sequence_id', seq_id, ...
                        'rx_pos',      rx_pos);
                    try
                        write(srv, uint8([jsonencode(req), newline]));
                        raw_resp = read_json_line(srv, SERVER_TIMEOUT);
                        resp     = jsondecode(raw_resp);

                        if strcmp(resp.status, 'ok')
                            fs_server   = double(resp.fs);
                            filters_raw = double(resp.filters);

                            if ALLOW_RESAMPLE && abs(fs_server - fs_device) > 1
                                filters = resample_filter_bank( ...
                                    filters_raw, fs_server, fs_device, NUM_CHANNELS);
                            else
                                filters = filters_raw;
                            end

                            zi = init_filter_state(filters, NUM_CHANNELS);

                            fprintf('  seq=%-4d  pos=[%+.2f %+.2f %+.2f]  shape=[%d×%d]  elapsed=%.0fms\n', ...
                                seq_id, rx_pos(1), rx_pos(2), rx_pos(3), ...
                                size(filters,1), size(filters,2), resp.elapsed_ms);

                            seq_id = seq_id + int32(1);
                        else
                            fprintf('[warn] Server error: %s\n', resp.message);
                        end
                    catch err
                        fprintf('[warn] Server comms failed: %s\n', err.message);
                    end
                    rx_pos = [];
            end
        end

        % --- 3. Build and play audio chunk ---
        switch MODE

            case 'delay'
                tones = apply_delay_sum(h, w, tau, fs_device, NUM_CHANNELS);

            case 'avdar'
                tones = zeros(N, NUM_CHANNELS);
                for ch = 1:NUM_CHANNELS
                    [tones(:,ch), zi{ch}] = filter(filters(:,ch), 1, h, zi{ch});
                end
        end

        peak = max(abs(tones(:)));
        if peak > 1
            tones = tones / peak;
        end

        playRec(tones);
    end
end


% ================================================================
% Local functions
% ================================================================

function [w, tau] = delay_sum_weights(rx_pos, spk_pos, c)
% delay_sum_weights  Compute per-channel amplitude weights and delays.
%
%   rx_pos  : [1×3] head position in meters (camera frame)
%   spk_pos : [M×3] speaker positions in meters (same frame)
%   c       : speed of sound in m/s
%
%   w   : [M×1] amplitude weights, normalized so max = 1
%   tau : [M×1] delays in seconds, normalized so min = 0

    diffs = spk_pos - rx_pos;                  % [M, 3]
    dists = sqrt(sum(diffs .^ 2, 2));          % [M, 1]
    dists = max(dists, 1e-3);                  % guard divide-by-zero

    tau = dists / c;
    tau = tau - min(tau);                      % normalize: nearest speaker = 0

    w = 1 ./ dists;
    w = w / max(w);                            % normalize: loudest = 1
end


function tones = apply_delay_sum(h, w, tau, fs, num_ch)
% apply_delay_sum  Apply integer-sample delays and weights to mono signal h.
%
%   h       : [N×1] mono source chunk
%   w       : [M×1] amplitude weights
%   tau     : [M×1] delays in seconds (min = 0)
%   fs      : sample rate
%   num_ch  : number of channels M
%
%   tones   : [N×M] multichannel output

    N = length(h);
    tones = zeros(N, num_ch);
    delay_samples = round(tau * fs);

    for ch = 1:num_ch
        d = delay_samples(ch);
        if d == 0
            tones(:, ch) = w(ch) * h;
        elseif d < N
            tones(d+1:end, ch) = w(ch) * h(1:end-d);
        end
        % d >= N: channel is silent this chunk (extreme delay, shouldn't happen)
    end
end


function line = read_json_line(srv, timeout_sec)
    buf      = uint8([]);
    deadline = tic;
    while true
        if toc(deadline) > timeout_sec
            error('beam_client:timeout', 'Server did not respond within %.1f s', timeout_sec);
        end
        avail = srv.NumBytesAvailable;
        if avail > 0
            buf = [buf, read(srv, avail, 'uint8')];  %#ok<AGROW>
            nl  = find(buf == uint8(10), 1);
            if ~isempty(nl)
                line = char(buf(1:nl-1));
                return;
            end
        else
            pause(0.001);
        end
    end
end


function zi = init_filter_state(filters, num_ch)
    L  = size(filters, 1);
    zi = cell(1, num_ch);
    for ch = 1:num_ch
        zi{ch} = zeros(max(L - 1, 1), 1);
    end
end


function filters_out = resample_filter_bank(filters_in, fs_in, fs_out, num_ch)
    [p, q]  = rat(fs_out / fs_in, 1e-4);
    col1    = resample(filters_in(:,1), p, q);
    filters_out = zeros(length(col1), num_ch);
    filters_out(:,1) = col1;
    for ch = 2:num_ch
        filters_out(:,ch) = resample(filters_in(:,ch), p, q);
    end
end
