import struct
def get_mp4_size(filename):
    with open(filename, 'rb') as f:
        data = f.read()
        tkhd_idx = data.find(b'tkhd')
        if tkhd_idx != -1:
            # skip version, flags, creation, modification, track_id, reserved, duration
            # etc. tkhd format:
            # width is at offset 76 (version 0) or 88 (version 1)
            version = data[tkhd_idx+4]
            offset = 76 if version == 0 else 88
            width = struct.unpack('>I', data[tkhd_idx+4+offset:tkhd_idx+4+offset+4])[0]
            height = struct.unpack('>I', data[tkhd_idx+4+offset+4:tkhd_idx+4+offset+8])[0]
            print(f"Width: {width>>16}.{width&0xffff}, Height: {height>>16}.{height&0xffff}")
        else:
            print("tkhd not found")

get_mp4_size("/home/hfy/APP/All_bot/test_data/202.mp4")
