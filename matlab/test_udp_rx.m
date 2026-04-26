% test_udp_rx.m
% Verify that MATLAB can receive and decode head position packets
% sent by netbridge (or the inject_position.py test script).
%
% Run inject_position.py on this machine in a separate terminal, then run
% this script in MATLAB.  Press Ctrl-C to stop.
%
% Expected output:
%   x=+0.042  y=+0.115  z=+1.203 m
%   x=+0.043  y=+0.114  z=+1.201 m
%   ...

UDP_PORT = 5007;

u = udpport('LocalPort', UDP_PORT);
fprintf('test_udp_rx: listening on UDP port %d  (Ctrl-C to stop)\n\n', UDP_PORT);

while true
    if u.NumBytesAvailable >= 12
        raw    = read(u, 12, 'uint8');
        floats = typecast(uint8(raw), 'single');   % 3 x float32 little-endian
        x = double(floats(1));
        y = double(floats(2));
        z = double(floats(3));
        fprintf('  x=%+.3f  y=%+.3f  z=%+.3f m\n', x, y, z);
    else
        pause(0.01);
    end
end
