# Module: default
# Author: jurialmunkey,matke
# License: GPL v.3 https://www.gnu.org/copyleft/gpl.html
if __name__ == '__main__':
    import sys
    from tmdbbingiehelper.lib.script.router import Script
    Script(*sys.argv[1:]).router()
