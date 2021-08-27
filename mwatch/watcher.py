
import os, sys, hashlib

class FileWatcher:

    def __init__(self, directory):
        self.directory = directory
        self.ldhash = None

    @staticmethod
    def hash_directory(base_directory):
        m = hashlib.md5()

        for root, dirs, files in os.walk(base_directory):
            # get append each file to hash
            for f in files:
                _,ext =os.path.splitext(f)
                # only hash python .py files
                if ext == ".py":
                    path = os.path.join(root,f)
                    m.update(open(path, 'rb').read())
        return m.hexdigest()

    def check(self):

        # get new hash
        dhash = self.hash_directory(self.directory)
        if self.ldhash is None:
            self.ldhash = dhash
            return False

        # on change
        if dhash != self.ldhash:
            self.ldhash = dhash
            return True
        
        return False

