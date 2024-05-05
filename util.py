""" Various functions used for unpacking, patching, and re-packing the QAD ROM """

from zipfile import ZipFile
import os
from os.path import join
import shutil
import hashlib

WORKING_DIR = join(".", "temp")
OUTPUT_DIR = join(".", "patched")
ZIP_FILENAME = "qad.zip"
ROM1A = "qdu_36a.12f"
ROM1B = "qdu_42a.12h"
ROM2A = "qdu_37a.13f"
ROM2B = "qdu_43a.13h"


def check_zip_hash(src_dir, fname):
    correct_hash = "0f2a54c9639d52120a76154eac2f0531964fbd1f7693614ca7c355468dedf6c5"
    hash = hashlib.sha256()
    with open(join(src_dir, fname), 'rb') as f:
        while True:
            data = f.read(65536)
            if not data:
                break
            hash.update(data)
    return hash.hexdigest() == correct_hash


def extract_zip(src_dir, fname):
    if os.path.isdir(WORKING_DIR):
        shutil.rmtree(WORKING_DIR)

    os.mkdir(WORKING_DIR)
    with ZipFile(join(src_dir, fname), 'r') as zip_f:
        zip_f.extractall(WORKING_DIR)


def add_dir_to_zip(zf, dir):
    """ https://stackoverflow.com/a/670635 """
    for file in os.listdir(dir):
        full_path = join(dir, file)
        if os.path.isfile(full_path):
            zf.write(full_path)
        elif os.path.isdir(full_path):
            add_dir_to_zip(zf, full_path)


def build_zip():
    os.chdir(WORKING_DIR)
    with ZipFile(join("..", "temp.zip"), "w") as zf:
        for file in os.listdir():
            if os.path.isfile(file):
                zf.write(file)
            else:
                add_dir_to_zip(zf, file)
    os.chdir("..")
    if os.path.isdir(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)

    os.mkdir(OUTPUT_DIR)

    # Copy uncompressed raw files to output dir too in order to make IPS patches
    for fn in [ROM1A, ROM1B, ROM2A, ROM2B]:
        shutil.copyfile(join(WORKING_DIR, fn), join(OUTPUT_DIR, fn))

    if os.path.isdir(WORKING_DIR):
        shutil.rmtree(WORKING_DIR)



    shutil.move("temp.zip", join(OUTPUT_DIR, "qad.zip"))


def deinterleave(fn1, fn2, outfn):
    """ Read 1 byte from fn1, 1 byte from fn2, 1 from fn1 etc until eof and write to out_fn """

    fp1 = open(join(WORKING_DIR, fn1), "rb")
    fp2 = open(join(WORKING_DIR, fn2), "rb")
    fps = [fp1, fp2]
    outfp = open(join(WORKING_DIR, outfn), "wb")

    i = 0
    while True:
        b = fps[i].read(1)
        if not b:
            break

        outfp.write(b)

        i = (i + 1) % 2

    fp1.close()
    fp2.close()
    outfp.close()


def interleave(fn, outfn1, outfn2):
    """ Opposite of deinterleave. Write every even byte from 'fn' to 'outfn1' and every odd byte to 'outfn2' """

    fp = open(join(WORKING_DIR, fn), "rb")
    outfp1 = open(join(WORKING_DIR, outfn1), "wb")
    outfp2 = open(join(WORKING_DIR, outfn2), "wb")
    outfps = [outfp1, outfp2]

    i = 0
    while True:
        b = fp.read(1)
        if not b:
            break

        outfps[i].write(b)
        i = (i + 1) % 2

    fp.close()
    outfp1.close()
    outfp2.close()


def concatenate(fn1, fn2, outfn):
    """ Write fn1 + fn2 to outfn """

    fp2 = open(join(WORKING_DIR, fn2), "rb")

    shutil.move(join(WORKING_DIR, fn1), join(WORKING_DIR, outfn))

    outfp = open(join(WORKING_DIR, outfn), "ab")
    outfp.write(fp2.read())

    fp2.close()
    outfp.close()


def split(fn, outfn1, outfn2, split_address):
    """
    Read 'fn' until the byte before 'split_address' and write to 'outfn1'. Then write remaining bytes to 'outfn2'.
    In other words, size of outfn1 will equal split_address.
    """

    fp = open(join(WORKING_DIR, fn), "rb")
    outfp1 = open(join(WORKING_DIR, outfn1), "wb")
    outfp2 = open(join(WORKING_DIR, outfn2), "wb")

    outfp1.write(fp.read(split_address))
    outfp2.write(fp.read())

    fp.close()
    outfp1.close()
    outfp2.close()


def patch(fn, address, patch_value=None, patch_fn=None):
    """
    Open 'fn' and replace bytes at 'address'. A hex string can be passed in to 'value', or a path to a binary file can
    be passed in to 'value_fn'. Filesize will not be changed.
    """

    if (not patch_value and not patch_fn) or patch_value and patch_fn:
        raise ValueError("patch function requires that either patch_value param or patch_fn is set, but not both.")

    if patch_value:
        replacement_bytes = patch_value
    else:
        with open(join(WORKING_DIR, patch_fn), "rb") as rep_f:
            replacement_bytes = rep_f.read()

    fp = open(join(WORKING_DIR, fn), "rb")
    temp_outf = open(join(WORKING_DIR, "in_place_edit.bin"), "wb")

    # Read up to the address that will change and write it
    temp_outf.write(fp.read(address))

    # Write the new bytes
    temp_outf.write(replacement_bytes)

    # Skip over the changed bytes and write the rest
    fp.seek(len(replacement_bytes), 1)
    temp_outf.write(fp.read())

    temp_outf.close()
    fp.close()

    os.remove(join(WORKING_DIR, fn))
    shutil.move(join(WORKING_DIR, "in_place_edit.bin"), join(WORKING_DIR, fn))
