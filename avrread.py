#########################################################################################################
#                                          AVRRead                                                      #
# A utility to read the XML files (probably .atdf in fact) in a Studio 6/7 installation and use         #
# the data within to define one big structure to overlay the SFR area of any AVR. Just use:             #
#                                                                                                       #
# python avrread.py -i ATmgea16.atdf                                                                    #
#                                                                                                       #
# or any other .atdf to generat an ATmega16.h (or whatever) header file for use in programming the      #
# AVR. In this case don't use "#include <avr/io.h>" but instead just do something like this:            #
#                                                                                                       #
#        #include "ATmega16.h"                                                                          #
#                                                                                                       #
#        USE_SFRS(pSFR);                                                                                #
#                                                                                                       #
#        int main(void)                                                                                 #
#        {                                                                                              #
#            pSFR->_DDRB.byte = 0xFF;                                                                   #
#            pSFR->_UCSRB.bit._TXEN = 1;                                                                #
#            while (1)                                                                                  #
#            {                                                                                          #
#                pSFR->_PORTB.byte ^= (1 << 3);                                                         #
#            }                                                                                          #
#        }                                                                                              #
#                                                                                                       #
# Use the USE_SFR() macro to name a struct pointer variable (like "pSFR") that you then want to         #
# use to access the registers in the code.                                                              #
#                                                                                                       #
#                        by Cliff Lawson                                                                #
#                                                                                                       #
# Licence: I need beer - see what you can do!                                                           #
#########################################################################################################

# following ("from...") line is useful if you are trying to make Python 3 code run in Python 2
# (however things like "argparse" here means this program is 3.2+ anyway.
# from __future__ import print_function
import sys
import os
import argparse
import xml.etree.ElementTree as et
from collections import namedtuple

doxy_template = '''
/**
 * @mainpage	The Atmel ##
 *
 * @details 	This is a complete definition of the layout of the ##
 *
 * @file
 * @brief      	These are the register/bit definitions:
 *
 * @copyright   Free for anyone to use
 * @author      Cliff Lawson
 */
'''

doxy_brief1 = "* @brief"
doxy_brief2 = ""
doxy_member = "*<"
doxy_whole = " /**< whole reg */"
doxy_bits = " /**< the bits */"
doxy_split = " /**< Split as two bytes */"
doxy_part_template = " /**< Complete register layout for ## */"

# found this on StackOverflow - it simply returns the lowest bit that is set in a byte
def lowestSet(int_type):
    ''' just testing a doc string '''
    low = (int_type & -int_type)
    lowBit = -1
    while (low):
        low >>= 1
        lowBit += 1
    return(lowBit)


# often find this useful to check the raw command line args
# for n in range(0, len(sys.argv)):
#	print(n, sys.argv[n])

# I like argparse - it makes for very clean command line interfaces
parser = argparse.ArgumentParser(description='Read Atmel XML (version 1.4)')
parser.add_argument("-i", "--input", dest='in_fname', help="name of .XML file to read as input")
parser.add_argument("-o", "--output", dest='out_name', help="Name of output file (overides default)")
parser.add_argument("-q", "--quiet", dest='quiet', action="store_true", help="Don't print to console")
parser.add_argument("-v", "--verbose", dest='verbose', action="store_true", help="Show developer info")
parser.add_argument("-m", "--multiple", dest='multiple', action="store_true", help="process multiple files")
parser.add_argument("-d", "--doxygen", dest='doxy', action="store_true", help="generate Doxygen style comments")
parser.add_argument("-s", "--symbols", dest='symbols', action="store_true", help="Generate a list of acronym symbols")

# my one argument with argparse is that if you run the app without args it doesn't show help info, so
# this will achieve that...
if len(sys.argv) == 1:
    parser.print_help()
    sys.exit(1)

# this actually runs the argument parser on sys.argv
args = parser.parse_args()

if args.doxy is not True:
    doxy_template = ""
    doxy_brief1 = "================"
    doxy_brief2 = " ================"
    doxy_member = ""
    doxy_whole = ""
    doxy_bits = ""
    doxy_split = ""

flist = []

if args.in_fname is not None and os.path.isfile(args.in_fname):
    flist.append(args.in_fname)
elif args.multiple is True and args.in_fname is None:
    for f in os.listdir("."):
        if ".atdf" in f:
            flist.append(f)

if len(flist) >= 1:
    for fname in flist:

        # split partname from input .atdf filename
        partname = os.path.splitext(fname)[0]

        if args.doxy:
            doxy_partname = doxy_part_template.replace("##", partname)
        else:
            doxy_partname = ""

        # The following creates an empty list. As the XML is parsed this will be appened()'d too to build a complete
        # picture of the AVR layout as a list of dictionaries
        mainlist = []

        # Assuming the user has given a name then do our thing!
        if fname is not None and os.path.isfile(fname):
            # the user has the opportunity to use -o to set an output filename but if they haven't used that this
            # takes the input .atdf/.xml filename and replaces the extension with ".h" to create the output name
            if args.out_name is None:
                out_name = partname + ".h"

            if args.multiple is True or args.quiet is not True:
                print("Creating:", out_name)
            # ===================================== PART 1 (process the XML) ======================================
            # following two lines are the classic way to invoke ElementTree to read an XML then get access to the
            # root from which access to all other data then occurs
            tree = et.parse(fname)
            root = tree.getroot()

            # So the first thing I search for is the "memory-segment" entry with attribute name='MAPPED_IO'
            # this has the start/length of the SFRs (start is bound to be 0x20, it's the length I need to
            # later build the struct that covers the entire SFR region)
            io_node = root.find(".//memory-segment[@name='MAPPED_IO']")
            sfr_start = io_node.attrib['start']
            sfr_size = io_node.attrib['size']

            # The "interesting stuff" (as far as this program is concerned) is then the "modules" which are things
            # like "UART", "TIMER_COUNTER_1" and so on.
            modules = root.find("modules")

            # this then iterates over each module found...
            for mod in modules.findall("module"):
                # rather curiously there are two "modules" called "FUSE" and "LOCKBIT" - I want to ignore them...
                if mod.attrib['name'] in ['FUSE', 'LOCKBIT']:
                    continue

                # To keep the user entertained with some output - print the name of each module as I find it...
                if not args.quiet:
                    print("===============", mod.attrib['name'], "===============")

                # Now there's a load of data for each "module" that I'm not interested in. All I want are the registers
                # and bits and these appear under one or more "register-groups"
                rg = mod.find("register-group")

                # then in each register group iterate through the individual registers..
                for reg in rg.findall("register"):
                    # for each register pick out the useful bits of information
                    addr = int(reg.attrib['offset'], 0)
                    name = reg.attrib['name']
                    capt = reg.attrib['caption']
                    if capt is None:
                        capt = "missing caption"
                    sz = int(reg.attrib['size'])
                    # only used for whole registers - some are not full 8 or 16 bits
                    try:
                        main_mask = int(reg.attrib['mask'], 0)
                    except KeyError:
                        if sz == 1:
                            main_mask = 0xFF
                        elif sz == 2:
                            main_mask = 0xFFFF

                    # use the following to add extra detail if more than one byte involved
                    xtra = ""
                    if sz != 1:
                        xtra = str(sz) + " bytes"
                    if not args.quiet:
                        print(name, "addr=", hex(addr), xtra, "// ", capt)

                    # Have a look to see if there is a "bitfield" defined for this register
                    bits = reg.findall("bitfield")

                    # going to create a list of tuples (eventually sorted and duplicates removed) for any groups of bits
                    bitlist = []
                    if len(bits) != 0:
                        # if there is/are bitfields then work through each entry in turn
                        for bit in bits:
                            # int(x, 0) converts "0xNN" into an integer value - unfortunately the XML only holds these
                            # as a "mask" so if it's bits 3,4,5,6 the mask will be 0x78 and so on - need to process this
                            # later to get the lowest bit (3 in this example) and the starting bit position. For the
                            # lowest bit set I found something useful on StackOverflow which is at the start of this file
                            # for the number of bits set in a mask I found a very clever technique in another answer
                            # on StackOverflow - you use bit() to convert the mask to a "10101.." string then use count('1')
                            # on this to find out how many bits there are (as it happens they're always adjacent in fact)
                            mask = int(bit.attrib['mask'], 0)
                            try:
                                captn = bit.attrib['caption']
                            except KeyError:
                                captn = "caption missing"
                            try:
                                lsb = int(bit.attrib['lsb'])
                            except KeyError:
                                lsb = 0
                            numbits = bin(mask).count('1')
                            # @@@ need to consider non-adjacent bits in a mask such as 0xB0 (10110000) - e.g. mega16 SM bits
                            # <thinks> - split the bits in a "multi-mask" at this stage and make multiple 1 bit appends
                            # rather than trying to unwind this later.
                            # OK change of plan - because entries like the SM bits have a mask of 0xB0 (10110000) with non-
                            # adjacent bits then don't just store the low bit and numbits, but iterate through the bitmask now
                            # and add individual :1 entries for multiple bits (adding the lsb suffix and an incrementing count)
                            if numbits == 1:
                                bitinfo = namedtuple("bitinfo", "bitpos name caption")
                                bitinfo.bitpos = lowestSet(mask)
                                bitinfo.name = bit.attrib['name']
                                bitinfo.caption = captn
                                bitlist.append(bitinfo)
                            else:
                                suffix = lsb  # this starts at 0 if there is no lsb=
                                bitpos = 0
                                while numbits:
                                    while mask & (1 << bitpos) == 0:
                                        bitpos += 1
                                    bitinfo = namedtuple("bitinfo", "bitpos name caption")
                                    bitinfo.bitpos = bitpos
                                    bitpos += 1
                                    bitinfo.name = bit.attrib['name'] + str(suffix)
                                    suffix += 1
                                    bitinfo.caption = captn
                                    bitlist.append(bitinfo)
                                    numbits -= 1

                        if not args.quiet:
                            for n in sorted(bitlist, key=lambda x: x.bitpos):
                                print(n.name, "bit=" + str(n.bitpos), n.caption)

                    # now we assume we are going to this register/bits as a whole new entry in mainlist[]. However it turns
                    # out the XML may have several different register/bit definitions in different places for the same
                    # register - but you can spot this because you have already seen the address used. (BTW this all occurs
                    # with a register like TIMSK that may have some TMR_0 bits defined under the section for "TIMER 0" but
                    # then has some more bits defined later under "TIMER 1" and so on)
                    do_add = 1

                    # so now we check to see if the address of the register we're currently looking at was already seen
                    # and recorded in mainlist[]. If it has been then what we need to do is extract the existing "bitlist"
                    # (which is a list of tuples), then append each new tuple we've just found to this. However that may
                    # lead to duplicates.
                    for n in mainlist:
                        if n['addr'] == addr:

                            # so pull the "bits" from the existing entry that was found to have the same address
                            updated_bits = n['bits']

                            # then append each new bit entry tuple to this..
                            for entry in bitlist:
                                do_add = 1
                                for eb in updated_bits:
                                    if entry.bitpos == eb.bitpos:
                                        do_add = 0
                                if do_add:
                                    updated_bits.append(entry)

                            # I'll leave this (one of my development print()s as I found it MOST useful!)
                            # print("YOIKS!", "now=", sorted(nodups))
                            # now search the entrie mainlist[] again to find the index (i) of the one where we found the
                            # existing entry for the same address
                            for i in range(0, len(mainlist)):

                                # and when we stumble upon it..
                                if mainlist[i]['addr'] == addr:

                                    # replace what was there with new details including the sorted, duplicate removed list of bits
                                    mainlist[i] = {'addr': addr, 'name': name, 'size': sz, 'main_mask': main_mask, 'caption': capt, 'bits': sorted(updated_bits, key=lambda x: x.bitpos)}

                            # as we've updated an existing entry we don't want to add the data as a new one so..
                            do_add = 0

                    # if the address has not occurred before then just add the details including the sorted list of bits -
                    # it sort by default on the first item in the tuple which is the bit position
                    if do_add:
                        mainlist.append({'addr': addr, 'name': name, 'size': sz, 'main_mask': main_mask, 'caption': capt, 'bits': sorted(bitlist, key=lambda x: x.bitpos)})

            # The order of the "modules" in the XML is arbitrary and does not follow address order so now we sort the mainlist
            # of dictionaries using the 'addr' field in each one. Again this clever technique came from Stack Overflow
            mainlist = sorted(mainlist, key=lambda k: k['addr'])

            # finally entertain the user with something interesting looking (good for debugging too!)
            if args.verbose:
                print("\n++++++++++ All of that data from XML now stored as.... +++++++++++\n")
                for ent in mainlist:
                    print(hex(ent['addr']), ent)

            # ===================================== PART 2 (generate the output) ======================================
            # So we arrive here with mainlist[] fully populated with the complete info of all registers/bits stripped
            #  from the XMLso and the list now ordered by address. Now it's time to generate some output
            regidx = 0

            # remember the "MAPPED_IO" which was the first thing taken from the XML - this is where we use the sfr_start/size
            # we pulled from it at that time
            addr = int(sfr_start, 0)

            # new options here -s/--symbols which uses the parsed list to generate an alpha sorted list of
            # acronyms/symbols. If we do this we don't want to generate the header so will bail out if we go
            # for this...
            if args.symbols:
                outsyms = []
                for entry in mainlist:
                    outsyms.append(entry['name'] + " = " + entry['caption'] + "\n")
                    if len(entry['bits']) != 0:
                        for bit in entry['bits']:
                            bitname = bit.name
                            suffix = ""
                            outsyms.append(bitname + " : bit within " + entry['name'] + " = " + bit.caption + "\n")
                outsyms.sort()
                out_name = out_name.replace(".h", ".sym")
                sym = open(out_name, "wt")
                for symstr in outsyms:
                    sym.write(symstr)
                sym.close()
                sys.exit(0)

            # this is just standard Python file IO - open xxx.h as a writable text file..
            hdr = open(out_name, "wt")

            hdr.write("#include <stdint.h>\n\n")
            doxy_text = doxy_template.replace("##", partname)

            # the preamble is a fixed text so write that now...
            if args.doxy is True:
                hdr.write(doxy_text + "\n\n")

            while regidx < len(mainlist):
                main_addr = mainlist[regidx]['addr']
                byts = int(mainlist[regidx]['size'])
                uint_sz = byts * 8
                main_mask = int(mainlist[regidx]['main_mask'])
                regbits = bin(main_mask).count('1')
                name = mainlist[regidx]['name']  # .lower()
                caption = mainlist[regidx]['caption']
                whole_reg = len(mainlist[regidx]['bits']) == 0
                hdr.write("/*" + doxy_brief1 + " " + name + " - " + caption + " @ " + str(hex(addr)).upper().replace('X','x') + doxy_brief2 + " */\n")
                if regbits == 8 or regbits == 16:
                    hdr.write("typedef union {\n\tuint" + str(uint_sz) + "_t reg;" + doxy_whole + "\n\tstruct {\n")
                else:
                    hdr.write("typedef union {\n\tunsigned int reg:" + str(regbits) + "; /*" + doxy_member + " (@ " + str(hex(addr)) + ") " + caption + " (range: 0.." + str((1 << regbits) - 1) + ") */\n\tstruct {\n")

                # now for a whole register just write bN fields for the number of bits there are
                if whole_reg:
                    for b in range(0,  bin(main_mask).count('1')):
                        hdr.write("\t\tunsigned int b" + str(b) + ":1;\n")
                else:
                    # So this is the complicated bit when there are named bits defined
                    bitpos = 0
                    for b in mainlist[regidx]['bits']:

                        # We have tuples like (2, 5, 'FOO') which means FOO is at bit position 2 and spans 5 bits but
                        # some of the structs have "gaps" that are unused and we need to fill these with padding
                        # the gap is padded using the following...
                        if b.bitpos > bitpos:
                            nskip = b.bitpos - bitpos
                            hdr.write("\t\tunsigned int       :" + str(b.bitpos - bitpos) + "; /*" + doxy_member + " b" + str(bitpos))
                            if nskip > 1:
                                hdr.write("...b" + str(b.bitpos - 1))
                            hdr.write(" - unused */\n")

                            # and step bitpos on to the bit position of the enrty we're about to write
                            bitpos = b.bitpos

                        # then the actual named "FOO:5" entry is created by this...
                        hdr.write("\t\tunsigned int _" + b.name + ":1; /*" + doxy_member + " b" + str(b.bitpos) + " " + b.caption + " */\n")

                        bitpos += 1  # b.numbits
                if uint_sz == 8:
                    # hdr.write("\t} bit;" + doxy_bits + "\n} " + name + "_t; /*" + doxy_member + " (@ " + str(hex(addr)) + ") " + caption + " */\n\n")
                    hdr.write("\t} bit;" + doxy_bits + "\n} " + name + "_t;\n\n")
                else:
                    # just assume/handle uint16_t for now..
                    hdr.write("\t} bit;" + doxy_bits + "\n")
                    hdr.write("\tstruct {\n")
                    hdr.write("\t\tuint8_t low;\n")
                    if regbits == 16:
                        hdr.write("\t\tuint8_t high;\n")
                    else:
                        hdr.write("\t\tunsigned int high:" + str(regbits - 8) + ";\n")
                    hdr.write("\t} halves;" + doxy_split + "\n")
                    #hdr.write("} " + name + "_t; /*"  + " (@ " + str(hex(addr)) + ") " + caption + " */\n\n")
                    hdr.write("} " + name + "_t;\n\n")

                # now step the mainlist[] index on to the next entry
                regidx += 1
                addr += byts - 1
                addr += 1

            regidx = 0

            addr = int(sfr_start, 0)

            hdr.write("\ntypedef struct {\n")
            # now we build a struct that will span sfr_start to sfr_start+sfr_size (remember int(x,0) converts "0xNN" to int)
            # Oh and if you are wondering why this is a while() loop and not a for() loop it's because in Python (I found
            # out the hard way!) you cannot use "for x in range(start,end)" and the modify x within the loop to skip some values
            # the range() builds a list at the very start and x will be set to every member in that list for each iteration
            # of the loop - updates to the iteration variable are over-written!
            while addr < (int(sfr_start, 0) + int(sfr_size, 0)):

                # now for each address in the SFR range we see if the next mainlist[] entry has something for it
                # first pull the mainlist entries into more readable varaible names:
                main_addr = mainlist[regidx]['addr']
                byts = int(mainlist[regidx]['size'])
                uint_sz = byts * 8
                main_mask = int(mainlist[regidx]['main_mask'])
                regbits = bin(main_mask).count('1')
                name = mainlist[regidx]['name']  # .lower()
                caption = mainlist[regidx]['caption']
                if main_addr == addr:
                    tab2 = ""
                    if len(name) < 6:
                        tab2 = "\t"
                    hdr.write("\t" + name + "_t\t" + tab2 + "_" + name + "; /*" + doxy_member + " (@ " + str(hex(addr)) + ") " + caption + " */\n")

                    # following adds 0 for size:1 entries but is mainly here for multi-byte entries so that addr can be
                    # stepped on for uint16_t registers and so on
                    addr += byts - 1

                    # now step the mainlist[] index on to the next entry
                    regidx += 1

                    # this may look "odd" but it prevents regidx trying to index beyond the end of mainlist and setting it
                    # to 1 is benign as "addr" has already moved on so there's no chance of it matching as it's now "behind"
                    # (hope that makes sense!)
                    if regidx >= len(mainlist):
                        regidx = 1
                else:
                    # this just writes an unused0xNN entry for each byte that has nothing in mainlist[]
                    hdr.write("\tuint8_t\t\tunused" + str(hex(addr)) + ";\n")
                addr += 1

            # then just finish with the closing part of the struct{} definition and we're all done! :-)
            # BTW I wanted to call the whole thing "AVR" not "SFRS" but the compiler alredy defines "AVR"
            hdr.write("} " + partname + ";" + doxy_partname + "\n\n")
            hdr.write("/** This must be used in your file to use these definitions */\n")
            hdr.write("#define USE_SFRS() volatile " + partname + " * const pSFR = (" + partname + " *)" + sfr_start + "\n\n")

            if args.doxy is True:
                hdr.write("#ifndef __DOXYGEN__\n")
            # now to make some easier to type/read symbols that actually hide some of that implementation
            for entry in mainlist:
                name = entry['name']
                hdr.write("/* ================= (" + name + ") " + entry['caption'] + " ================ */\n")
                hdr.write("#define " + name.lower() + " pSFR->_" + name + ".reg\n")
                if len(entry['bits']) == 0:
                    for n in range(0, bin(entry['main_mask']).count('1')):
                        hdr.write("#define " + name.lower() + "_b" + str(n) + " pSFR->_" + name + ".bit.b" + str(n) + "\n")
                    # assume it's uint16_t so there are two "halves" too:
                    if int(entry['size']) > 1:
                        hdr.write("#define " + name.lower() + "l pSFR->_" + name + ".halves.low\n")
                        hdr.write("#define " + name.lower() + "h pSFR->_" + name + ".halves.high\n")

                else:
                    for bit in entry['bits']:
                        bitname = bit.name.lower()
                        hdr.write("#define " + name.lower() + "_" + bitname + " pSFR->_" + name + ".bit._" + bitname.upper() + "\n")
                    for bit in entry['bits']:
                        bitname = bit.name.lower()
                        suffix = ""
                        if name == "SREG":
                            suffix = "_flag"
                        hdr.write("#define " + bitname + suffix + " (1 << " + str(bit.bitpos) + ")\n")
                    for bit in entry['bits']:
                        bitname = bit.name.lower()
                        hdr.write("#define " + bitname + "_bp " + str(bit.bitpos) + "\n")
                hdr.write("\n")
            if args.doxy is True:
                hdr.write("#endif /*__DOXYGEN__*/\n")
            hdr.close()
        else:
            print("No valid input file")
