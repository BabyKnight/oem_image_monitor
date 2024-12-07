import ctypes

lib = ctypes.CDLL('./liblp_auth.so')

lib.get_username.restype = ctypes.c_char_p
lib.get_password.restype = ctypes.c_char_p

username = lib.get_username()
password = lib.get_password()
