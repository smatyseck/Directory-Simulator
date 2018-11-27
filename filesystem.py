from os import listdir
import win32api


class Disk:
    def __init__(self):
        self.disk = []
        self.openfiletable = [[bytearray(64), 0, 1], [bytearray(64), 0, 0], [bytearray(64), 0, 0],
                              [bytearray(64), 0, 0]]
        # (read/write buffer, Current pos, file descriptor index)
        for i in range(64):  # initialize disk
            self.disk.append(bytearray(64))
        for i in range(1, 7):  # set descriptor bytes to xFF to allow for checking what descriptors are free
            for j in range(64):
                self.disk[i][j] = 255
        for i in range(7):  # initialize the allocations of the bitmap for descriptor arrays
            self.disk[0][i] = 1

    def read_block(self, i, ch):
        # Copy from disk[i] into ch (a bytearray of length 64 bytes) byte by byte
        for j in range(64):
            ch[j] = self.disk[i][j]
        return 0

    def write_block(self, i, ch):
        # Copy from ch (a bytearray of length 64 bytes) into disk[i]
        for j in range(64):
            self.disk[i][j] = ch[j]
        return 0

    def createfile(self, filename):
        if len(filename) <= 3:
            # read in block containing directory descriptor
            mem_loc = bytearray(64)
            self.read_block(1, mem_loc)
            dir_len = int.from_bytes(mem_loc[0:4], byteorder='big', signed=True)
            if dir_len == -1 or dir_len / 8 == 0:
                # directory is size -1 so must allocate first block
                bm = bytearray(64)
                self.read_block(0, bm)
                b_index = -1
                for i in range(7, 64):
                    if bm[i] == 0:
                        b_index = i
                        break
                dir_len = 1
                for b, byte in zip(range(4), dir_len.to_bytes(4, byteorder='big')):
                    # pack dir_len into file_length section of descriptor
                    mem_loc[b] = byte
                for b, byte in zip(range(4), b_index.to_bytes(4, byteorder='big')):
                    # pack b_index into 1st block# section of descriptor
                    mem_loc[b + 4] = byte
                bm[b_index] = 1
                self.write_block(0, bm)
                self.write_block(1, mem_loc)
            mem_loc2 = bytearray(64)
            descriptor_index = -1
            i = 0
            while descriptor_index == -1 and i < 7:
                # need to iterate through descriptors to find an available slot
                i += 1
                self.read_block(i, mem_loc2)
                j = 0
                while j < 64:
                    file_len = int.from_bytes(mem_loc2[j:j + 4], byteorder='big', signed=True)
                    if file_len == -1:
                        # unallocated so save this
                        descriptor_index = int(j / 16)
                        file_len = 0
                        for b, byte in zip(range(4), file_len.to_bytes(4, byteorder='big')):
                            mem_loc2[b + j] = byte
                        break
                    j += 16  # descriptors have length of 4 ints
                if descriptor_index > -1:
                    descriptor_index += (i - 1) * 4
            d_block = i
            if descriptor_index == -1:
                return -1
            if descriptor_index < 24 and descriptor_index > 8 and int(descriptor_index - 1) % 8 == 0:
                # need new allocation
                bm = bytearray(64)
                self.read_block(0, bm)
                b_index = -1
                for i in range(7, 64):
                    if bm[i] == 0:
                        b_index = i
                        break
                dir_len += 1
                for b, byte in zip(range(4), dir_len.to_bytes(4, byteorder='big')):
                    # pack dir_len into file_length section of descriptor
                    mem_loc[b] = byte
                for b, byte in zip(range(4), b_index.to_bytes(4, byteorder='big')):
                    # pack b_index into block# section of descriptor
                    mem_loc[b + 4 * dir_len] = byte
                bm[b_index] = 1
                self.write_block(0, bm)
                self.write_block(1, mem_loc)
            mem_loc3 = bytearray(64)
            for i in range(1, dir_len + 1):
                index = int.from_bytes(mem_loc[i * 4:i * 4 + 4], byteorder='big')
                self.read_block(index, mem_loc3)  # read in directory file
                j = 0
                while j < 64:
                    # iterate over possible directory entries and check if file already exists
                    if mem_loc3[j:j + 4].decode().strip() == filename:
                        return -1
                    if mem_loc3[j] == 0:
                        # if entry
                        for s in range(4):
                            # write filename char by char
                            try:
                                mem_loc3[j + s] = ord(filename[s])
                            except:
                                sp = ' '
                                mem_loc3[j + s] = ord(sp)
                        for b, byte in zip(range(4), descriptor_index.to_bytes(4, byteorder='big')):
                            # pack descriptor_index into byte array
                            mem_loc3[j + 4 + b] = byte
                        self.write_block(index, mem_loc3)
                        break
                    j += 8  # iterate over descriptor index
            self.write_block(d_block, mem_loc2)
            return filename + ' created'
        return -1

    def destroyfile(self, filename):
        descriptor_index = -1
        dir_block = bytearray(64)
        mem_loc2 = bytearray(64)
        self.read_block(1, dir_block)
        dir_len = int.from_bytes(dir_block[0:4], byteorder='big', signed=True)
        b = False  # dummy variable to double break
        for i in range(1, dir_len + 1):  # iterate through directory blocks and try to find the file
            ind = int.from_bytes(dir_block[i * 4:i * 4 + 4], byteorder='big')
            self.read_block(ind, mem_loc2)
            j = 0
            while j < 64:
                if mem_loc2[j:j + 4].decode().strip() == filename:
                    descriptor_index = int.from_bytes(mem_loc2[j + 4:j + 8], byteorder='big')
                    for x in range(8):  # found file so clear file name and descriptor number from block
                        mem_loc2[x + j] = 0
                    self.write_block(ind, mem_loc2)
                    b = True
                    break
                j += 8
            if b:
                break
        if descriptor_index == -1:  # if file doesn't exist, error
            return -1
        for i in range(1, 4):  # if file is open, close it
            if self.openfiletable[i][2] == descriptor_index:
                self.openfiletable[i] = [bytearray(64), 0, 0]
                break
        file_block = bytearray(64)
        self.read_block(int(descriptor_index / 4) + 1, file_block)
        offset = descriptor_index % 4
        file_len = int.from_bytes(file_block[offset * 16:offset * 16 + 4], byteorder='big', signed=True)
        bm = bytearray(64)
        self.read_block(0, bm)
        for i in range(1, int(file_len/64) + 1):  # iterate through the blocks of the file, zeroing all blocks
            num = int.from_bytes(file_block[offset * 16 + 4 * i:offset * 16 + 4 + 4 * i], byteorder='big', signed=True)
            bm[num] = 0
            self.write_block(num, bytearray(64))
        self.write_block(0, bm)
        for i in range(16):  # set file descriptor back to unallocated
            file_block[offset * 16 + i] = 255
        self.write_block(int(descriptor_index / 4) + 1, file_block)
        return filename + ' destroyed'

    def openfile(self, filename):
        index = 0
        for i in range(1, 4):
            if self.openfiletable[i][2] == 0 and index == 0:  # find available spot in OFT
                index = i
        if index == 0:
            return -1
        if index != 0:
            descriptor_index = -1
            dir_block = bytearray(64)
            mem_loc2 = bytearray(64)
            self.read_block(1, dir_block)
            dir_len = int.from_bytes(dir_block[0:4], byteorder='big', signed=True)
            for i in range(1, dir_len + 1):  # iterate through directory blocks to find file
                ind = int.from_bytes(dir_block[i * 4:i * 4 + 4], byteorder='big')
                self.read_block(ind, mem_loc2)
                j = 0
                while j < 64:
                    if mem_loc2[j:j + 4].decode().strip() == filename:  # file found
                        descriptor_index = int.from_bytes(mem_loc2[j + 4:j + 8], byteorder='big')
                    j += 8
            if descriptor_index == -1:  # if no free descriptor, error
                return -1
            for i in range(1, 4):
                if self.openfiletable[i][2] == descriptor_index:  # check if file is already open
                    return -1
            self.openfiletable[index][2] = descriptor_index
        file_block = bytearray(64)
        self.read_block(int(descriptor_index / 4) + 1, file_block)
        offset = descriptor_index % 4
        file_len = int.from_bytes(file_block[offset * 16:offset * 16 + 4], byteorder='big', signed=True)
        first = int.from_bytes(file_block[offset * 16 + 4:offset * 16 + 8], byteorder='big', signed=True)
        if first == -1:  # first time opening, need to allocate new block to read ahead
            bm = bytearray(64)
            self.read_block(0, bm)
            b_index = -1
            for i in range(7, 64):  # find unallocated block
                if bm[i] == 0:
                    b_index = i
                    break
            if b_index == -1:  # if no block was free, can't open so error
                self.openfiletable[index][2] = 0  # undo descriptor in OFT
                return -1
            for b, byte in zip(range(4), b_index.to_bytes(4, byteorder='big')):
                # pack b_index into 1st block# section of descriptor
                file_block[offset * 16 + b + 4] = byte
            bm[b_index] = 1
            self.write_block(0, bm)
            self.write_block(int(descriptor_index / 4) + 1, file_block)
        first_block = int.from_bytes(file_block[offset * 16 + 4:offset * 16 + 8], byteorder='big')
        self.read_block(first_block, self.openfiletable[index][0])
        return filename + ' opened ' + str(index)

    def closefile(self, index):
        if self.openfiletable[index][2] == 0:  # No file open or trying to close directory
            return -1
        self.openfiletable[index] = [bytearray(64), 0, 0]
        return str(index) + " closed"

    def read(self, file, amount):
        if file != 0 and self.openfiletable[file][2] == 0:
            return -1
        file_block = bytearray(64)
        descriptor_index = int(self.openfiletable[file][2])
        self.read_block(int(descriptor_index / 4) + 1, file_block)
        offset = descriptor_index % 4
        file_len = int.from_bytes(file_block[offset * 16:offset * 16 + 4], byteorder='big', signed=True)
        relative_block = int(int(self.openfiletable[file][1]) / 64) + 1
        if relative_block > 3:
            return ''
        block = int.from_bytes(
                file_block[offset * 16 + 4 * relative_block:offset * 16 + 4 * relative_block + 4],
                byteorder='big', signed=True)
        if block == -1:
            return -1
        self.read_block(block, self.openfiletable[file][0])  # read approriate block into buffer
        total = 0
        i = self.openfiletable[file][1] % + 64
        r = ''
        while total < amount:
            if self.openfiletable[file][1] > file_len - 1:  # if no more information written in block
                break
            r += chr(self.openfiletable[file][0][i])
            total += 1
            i += 1
            self.openfiletable[file][1] += 1
            if i == 64:  # end of buffer, get next block
                relative_block = int(int(self.openfiletable[file][1]) / 64) + 1
                if relative_block > 3 or self.openfiletable[file][1] > file_len:
                    # no need to get next block if it doesn't or can't exist
                    break
                block = int.from_bytes(
                        file_block[offset * 16 + 4 * relative_block:offset * 16 + 4 * relative_block + 4],
                        byteorder='big', signed=True)
                i = 0
                self.read_block(block, self.openfiletable[file][0])  # read next block into buffer
        return r

    def write(self, file, char, amount):
        if self.openfiletable[file][2] == 0:
            return -1
        file_block = bytearray(64)
        descriptor_index = int(self.openfiletable[file][2])
        self.read_block(int(descriptor_index / 4) + 1, file_block)
        offset = descriptor_index % 4
        file_len = int.from_bytes(file_block[offset * 16:offset * 16 + 4], byteorder='big', signed=True)
        relative_block = int(int(self.openfiletable[file][1]) / 64) + 1
        if relative_block > 3:
            return "0 bytes written"
        block = int.from_bytes(
                file_block[offset * 16 + 4 * relative_block:offset * 16 + 4 * relative_block + 4],
                byteorder='big', signed=True)
        total = 0
        i = self.openfiletable[file][1] % 64  # set i to current pos in buffer
        self.read_block(block, self.openfiletable[file][0])  # read approriate block into buffer
        while total < amount:
            if self.openfiletable[file][1] >= (64 * 3):
                break
            self.openfiletable[file][0][i] = ord(char)  # write character to buffer as byte
            total += 1
            self.openfiletable[file][1] += 1
            i += 1
            if self.openfiletable[file][1] > file_len:
                file_len = self.openfiletable[file][1]
                for b, byte in zip(range(4), file_len.to_bytes(4, byteorder='big')):
                    # pack dir_len into file_length section of descriptor
                    file_block[offset * 16 + b] = byte
                self.write_block(int(descriptor_index / 4) + 1, file_block)
            if i == 64:  # end of buffer, load next block
                relative_block = int(int(self.openfiletable[file][1]) / 64) + 1
                if file_len < relative_block * 64:  # if the next block doesnt exist, allocate another block
                    if relative_block > 3: # file too long
                        break
                    bm = bytearray(64)
                    self.read_block(0, bm)
                    b_index = -1
                    for i in range(7, 64):  # find next available block
                        if bm[i] == 0:
                            b_index = i
                            break
                    if b_index == -1:
                        break
                    for b, byte in zip(range(4), b_index.to_bytes(4, byteorder='big')):
                        # pack b_index into block# section of descriptor
                        file_block[offset * 16 + b + 4 + 4 * (relative_block - 1)] = byte
                    bm[b_index] = 1
                    self.write_block(0, bm)
                    self.write_block(int(descriptor_index / 4) + 1, file_block)
                self.write_block(block, self.openfiletable[file][0])  # write buffer to disk
                block = int.from_bytes(
                        file_block[offset * 16 + 4 * relative_block:offset * 16 + 4 * relative_block + 4],
                        byteorder='big', signed=True)  # get next block
                i = 0  # reset relative position
                self.read_block(block, self.openfiletable[file][0])  # read next block to buffer
        self.write_block(block, self.openfiletable[file][0])  # write buffer to disk
        return str(total) + ' bytes written'

    def seek(self, index, pos):
        if self.openfiletable[index][2] != 0:  # if there is a file open at the given index, check if valid pos
            file_block = bytearray(64)
            descriptor_index = int(self.openfiletable[index][2])
            self.read_block(int(descriptor_index / 4) + 1, file_block)
            offset = descriptor_index % 4
            file_len = int.from_bytes(file_block[offset * 16:offset * 16 + 4], byteorder='big', signed=True)
            if pos <= file_len:
                self.openfiletable[index][1] = pos
                return 'position is ' + str(pos)
        return -1

    def listfiles(self):
        files = ''  # variable to store file names
        directory = bytearray(64)
        self.read_block(1, directory)
        dir_len = int.from_bytes(directory[0:4], byteorder='big', signed=True)
        for i in range(1, dir_len + 1):  # iterate through blocks allocated to directory
            block_num = int.from_bytes(directory[4 * i:4 * i + 4],
                                       byteorder='big', signed=True)
            block = bytearray(64)
            self.read_block(block_num, block)
            j = 0
            while j < 64:  # iterate through block finding file names
                if block[j] != 0:  # file name found
                    name = block[j:j + 4].decode().strip()
                    files += name + ' '
                j += 8  # iterate to next possible file name location
        return files.strip()

    def save(self):
        # Close all files with save command
        self.openfiletable = [[bytearray(64), 0, 0], [bytearray(64), 0, 0], [bytearray(64), 0, 0],
                              [bytearray(64), 0, 0]]
        mem_loc = bytearray(64)
        # read in first block and convert to hex
        self.read_block(0, mem_loc)
        output = mem_loc.hex()  #
        for block in range(1, 64):  # read in all other blocks, convert to hex and append with a comma
            self.read_block(block, mem_loc)
            output += ',' + mem_loc.hex()
        return output

    def load(self, diskstring):
        blocks = diskstring.split(sep=',')
        for i in range(64):  # iterate through blocks list and write each block to disk
            block = bytearray.fromhex(blocks[i])
            self.write_block(i, block)


class Shell:
    def initialize_disk(self):
        self.disk = Disk()
        return "disk initialized"

    def create_file(self, file_name):
        return self.disk.createfile(file_name)

    def destroy_file(self, file_name):
        return self.disk.destroyfile(file_name)

    def open_file(self, file_name):
        return self.disk.openfile(file_name)

    def close_file(self, index):
        return self.disk.closefile(int(index))

    def read_file(self, file_no, count):
        return self.disk.read(int(file_no), int(count))

    def write_file(self, file_no, char, count):
        return self.disk.write(int(file_no), char, int(count))

    def seek_file(self, file_no, pos):
        return self.disk.seek(int(file_no), int(pos))

    def list_files(self):
        return self.disk.listfiles()

    def load_disk(self, file_name):
        try:
            f = open(file_name)
        except:
            return -1
        self.disk = Disk()
        try:
            r = self.disk.load(f.readline().strip())
        except IndexError:  # Catches an invalid disk file
            return -1
        f.close()
        return "disk restored"

    def save_disk(self, file_name):
        info = self.disk.save()
        f = open(file_name, 'w+')
        f.write(info)
        f.close()
        return "disk saved"

    def decode_command(self, input_string):
        cmd = input_string.split()
        if len(cmd) == 0:
            return ''
        r = -1
        try:
            if cmd[0] == 'cr':
                r = self.create_file(cmd[1])
            elif cmd[0] == 'de':
                r = self.destroy_file(cmd[1])
            elif cmd[0] == 'op':
                r = self.open_file(cmd[1])
            elif cmd[0] == 'cl':
                r = self.close_file(cmd[1])
            elif cmd[0] == 'rd':
                r = self.read_file(cmd[1], cmd[2])
            elif cmd[0] == 'wr':
                r = self.write_file(cmd[1], cmd[2], cmd[3])
            elif cmd[0] == 'sk':
                r = self.seek_file(cmd[1], cmd[2])
            elif cmd[0] == 'dr':
                r = self.list_files()
            elif cmd[0] == 'in':
                if len(cmd) == 1:
                    r = self.initialize_disk()
                else:
                    r = self.load_disk(cmd[1])
            elif cmd[0] == 'sv':
                r = self.save_disk(cmd[1])
        except (IndexError, AttributeError):  # catches not enough arguments and disk not being initialized
            r = -1
        if r == -1:
            return "error"
        #print(self.disk.disk)
        r = r.strip()
        return r


if __name__ == '__main__':
    drives = win32api.GetLogicalDriveStrings()
    drives = drives.split('\000')[:-1]
    input = 'input.txt'
    output = 'output.txt'
    for drive in drives:
        try:
            for f in listdir(drive):
                if f == 'input.txt':
                    input = drive + 'input.txt'
                    output = drive + 'output.txt'
        except:
            pass
    file = open(input)
    shell = Shell()
    commands = file.readlines()
    file.close()
    file = open(output, 'w+')
    first = True
    for command in commands:
        r = shell.decode_command(command.strip())
        if first and len(r) > 0:
            file.write(r)
            first = False
        else:
            file.write('\n' + r)
    file.close()
