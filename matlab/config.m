% config.m — shared runtime constants for beam_client
% Run this file (or call it from beam_client) before starting.

% --- Operating mode ---
% 'delay' : local delay-and-sum, no GPU server required.
%           Only needs: netbridge + MATLAB.
% 'avdar'  : AV-DAR matched-filter FIR via GPU server.
%           Needs: SSH tunnel + GPU server + netbridge + MATLAB.
MODE            = 'delay';

% --- Speaker positions (camera coordinate frame) ---
% x = right, y = down, z = forward, units = meters.
% Origin = RealSense camera lens.
% REPLACE PLACEHOLDERS with measured values.
%
% Row order matches MCHStreamer channel order:
%   row 1 -> channel 1, row 2 -> channel 2, etc.
% 4 speakers, equally spaced, 6-inch (0.1524 m) horizontal line.
% Spacing: 2 inches (0.0508 m) between adjacent speakers.
% x positions are fixed; measure y (height) and z (distance forward
% from camera) and replace the TODO values.
% 4 speakers, equally spaced, 6-inch (0.1524 m) horizontal line.
% Spacing: 2 inches (0.0508 m). Array center is 8 cm above camera, same depth.
SPEAKER_POSITIONS_M = [
   -0.0762, -0.08,  0.00;   % speaker 1 (leftmost)
   -0.0254, -0.08,  0.00;   % speaker 2
    0.0254, -0.08,  0.00;   % speaker 3
    0.0762, -0.08,  0.00;   % speaker 4 (rightmost)
];

SPEED_OF_SOUND  = 343.0;   % m/s at ~20°C

% --- TCP connection to AV-DAR beamforming server (avdar mode only) ---
% Access via SSH tunnel: ssh -L 5005:127.0.0.1:5005 gpu-server
SERVER_HOST     = '10.137.180.141';
SERVER_PORT     = 5005;
SERVER_TIMEOUT  = 5;        % seconds to wait for server response
ALLOW_RESAMPLE  = true;     % resample FIR filters if server fs != device fs

% --- UDP port that netbridge sends head position to ---
% Payload: 12 bytes, little-endian float32[3] = [x, y, z] meters
UDP_POS_PORT    = 5007;

% --- Audio device ---
DEVICE_NAME     = 'MCHStreamer I2S TosLink';
NUM_CHANNELS    = 4;

% --- Source signal ---
TONE_FREQ       = 1000;     % Hz
CHUNK_DURATION  = 0.1;      % seconds per playback chunk
