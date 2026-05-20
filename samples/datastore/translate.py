#!/usr/bin/env python3
"""
Test program for coreconf-m2m model
Loads the SID file, generates random test data, and converts to CORECONF
"""

import sys
import os
import json
import random
import pprint


import pycoreconf

# Define transducer type identities (from the YANG model)



def main():
    """Main test function"""

 

    sid_path = "ietf-schc@2026-05-07-short.sid"

    print(f"\n[*] Loading SID file: {sid_path}")

    try:
        # Create the CORECONF model with the SID file
        ccm = pycoreconf.CORECONFModel(sid_path)
        print("[+] SID file loaded successfully")
    except Exception as e:
        print(f"[-] Error loading SID file: {e}")
        sys.exit(1)

    with open("atmos41-short.sor", "rb") as f:
        cbor_data = f.read()

    old_size = len(cbor_data)
    print(f"\n[*] Loaded CBOR data from 'atmos41-short.sor', size: {old_size} bytes")



    # Try to decode back
    print("\n[*] Decoding CBOR  to JSON...")
    try:
        decoded_json = ccm.decode(cbor_data)
        print("[+] Decoding successful")
        print("\n[*] Decoded JSON configuration:")
        print("-" * 70)
        print(json.dumps(decoded_json, indent=2))
        print("-" * 70)
    except Exception as e:
        print(f"[-] Error decoding CBOR: {e}")
        sys.exit(1)


    new_cbor_data = ccm.translate_sid(cbor_data)
    print (f"len(new_cbor_data)={len(new_cbor_data)}, old_size={old_size}")


if __name__ == "__main__":
    main()
