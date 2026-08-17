# Module: default
# Author: jurialmunkey,matke
# License: GPL v.3 https://www.gnu.org/copyleft/gpl.html
if __name__ == '__main__':
    import sys
    from tmdbbingiehelper.lib.items.router import Router
    Router(int(sys.argv[1]), sys.argv[2][1:]).run()
