deviceReader = audioDeviceReader;
devices = getAudioDevices(deviceReader);

device = 'MCHStreamer I2S TosLink';

playRec = audioPlayerRecorder('Device', device, 'BitDepth', '24-bit integer', 'PlayerChannelMapping', 1:4);

fs = playRec.SampleRate;
duration = 1;                    % seconds
t = (0:1/fs:duration-1/fs).';

tone = 0.5*sin(2*pi*1000*t);     % input signal h(t)

%% ===== General 4-channel beamforming: y_i(t) = w_i h(t - t_i) =====

h = tone;

% Beamforming weights: w1, w2, w3, w4
w = [1, 1, 1, 1];

% Per-channel delays in seconds: t1, t2, t3, t4
tau = [0, 0.0001, 0.0002, 0.0003];

M = 4;
N = length(h);

% Make all delays nonnegative
tau = tau - min(tau);

% Convert delay time to integer sample delay
delaySamples = round(tau * fs);

tones = zeros(N, M);

for ch = 1:M
    delay = delaySamples(ch);

    if delay == 0
        tones(:, ch) = w(ch) * h;
    else
        tones(delay+1:end, ch) = w(ch) * h(1:end-delay);
    end
end

% Avoid clipping
maxVal = max(abs(tones(:)));
if maxVal > 1
    tones = tones / maxVal;
end

%% ================================================================

% Play and record
playRec(tones);