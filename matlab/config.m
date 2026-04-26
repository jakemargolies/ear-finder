% config.m — shared runtime constants for beam_client
% Run this file (or call it from beam_client) before starting.

% --- Operating mode ---
% 'delay' : local delay-and-sum, no GPU server required.
%           Only needs: netbridge + MATLAB.
% 'avdar'  : AV-DAR matched-filter FIR via GPU server.
%           Needs: SSH tunnel + GPU server + netbridge + MATLAB.
MODE            = 'delay';

% --- Speaker x-positions along the horizontal array (meters, right = positive) ---
% 4 speakers, 5 cm center-to-center, 15 cm total span, centered on camera.
% Only x is needed for the far-field delay formula.
SPEAKER_X_M = [-0.075; -0.025; 0.025; 0.075];   % [4×1], left to right

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
