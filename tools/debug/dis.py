#!/usr/bin/env python3
"""SM83 disassembler for GBS payload. Usage: python dis.py <gbs> <hex_addr> [n_bytes]"""
import sys, struct

def dis(data, data_base, target, n):
    """data: bytearray, data_base: ROM address of data[0], target: start addr, n: bytes"""
    i = target - data_base
    ops = []
    end = i + n
    while i < end and i < len(data):
        addr = data_base + i
        b = data[i]
        def b1(): return data[i+1]
        def b2(): return (data[i+2] << 8) | data[i+1]
        def jr(): offs = data[i+1]; return offs if offs < 128 else offs - 256

        if   b == 0xFA: ops.append((addr, f'LD A, (${b2():04X})')); i+=3
        elif b == 0xEA: ops.append((addr, f'LD (${b2():04X}), A')); i+=3
        elif b == 0xC3: ops.append((addr, f'JP ${b2():04X}')); i+=3
        elif b == 0xCA: ops.append((addr, f'JP Z, ${b2():04X}')); i+=3
        elif b == 0xC2: ops.append((addr, f'JP NZ, ${b2():04X}')); i+=3
        elif b == 0xDA: ops.append((addr, f'JP C, ${b2():04X}')); i+=3
        elif b == 0xD2: ops.append((addr, f'JP NC, ${b2():04X}')); i+=3
        elif b == 0xCD: ops.append((addr, f'CALL ${b2():04X}')); i+=3
        elif b == 0xCC: ops.append((addr, f'CALL Z, ${b2():04X}')); i+=3
        elif b == 0xC4: ops.append((addr, f'CALL NZ, ${b2():04X}')); i+=3
        elif b == 0xDC: ops.append((addr, f'CALL C, ${b2():04X}')); i+=3
        elif b == 0x21: ops.append((addr, f'LD HL, ${b2():04X}')); i+=3
        elif b == 0x11: ops.append((addr, f'LD DE, ${b2():04X}')); i+=3
        elif b == 0x01: ops.append((addr, f'LD BC, ${b2():04X}')); i+=3
        elif b == 0x31: ops.append((addr, f'LD SP, ${b2():04X}')); i+=3
        elif b == 0x08: ops.append((addr, f'LD (${b2():04X}), SP')); i+=3
        elif b == 0x3E: ops.append((addr, f'LD A, ${b1():02X}')); i+=2
        elif b == 0x06: ops.append((addr, f'LD B, ${b1():02X}')); i+=2
        elif b == 0x0E: ops.append((addr, f'LD C, ${b1():02X}')); i+=2
        elif b == 0x16: ops.append((addr, f'LD D, ${b1():02X}')); i+=2
        elif b == 0x1E: ops.append((addr, f'LD E, ${b1():02X}')); i+=2
        elif b == 0x26: ops.append((addr, f'LD H, ${b1():02X}')); i+=2
        elif b == 0x2E: ops.append((addr, f'LD L, ${b1():02X}')); i+=2
        elif b == 0x36: ops.append((addr, f'LD (HL), ${b1():02X}')); i+=2
        elif b == 0xE0: ops.append((addr, f'LDH ($FF{b1():02X}), A')); i+=2
        elif b == 0xF0: ops.append((addr, f'LDH A, ($FF{b1():02X})')); i+=2
        elif b == 0x18: ops.append((addr, f'JR ${addr+2+jr():04X}')); i+=2
        elif b == 0x20: ops.append((addr, f'JR NZ, ${addr+2+jr():04X}')); i+=2
        elif b == 0x28: ops.append((addr, f'JR Z, ${addr+2+jr():04X}')); i+=2
        elif b == 0x30: ops.append((addr, f'JR NC, ${addr+2+jr():04X}')); i+=2
        elif b == 0x38: ops.append((addr, f'JR C, ${addr+2+jr():04X}')); i+=2
        elif b == 0xC6: ops.append((addr, f'ADD A, ${b1():02X}')); i+=2
        elif b == 0xD6: ops.append((addr, f'SUB ${b1():02X}')); i+=2
        elif b == 0xE6: ops.append((addr, f'AND ${b1():02X}')); i+=2
        elif b == 0xF6: ops.append((addr, f'OR ${b1():02X}')); i+=2
        elif b == 0xEE: ops.append((addr, f'XOR ${b1():02X}')); i+=2
        elif b == 0xFE: ops.append((addr, f'CP ${b1():02X}')); i+=2
        elif b == 0xCE: ops.append((addr, f'ADC A, ${b1():02X}')); i+=2
        elif b == 0xDE: ops.append((addr, f'SBC A, ${b1():02X}')); i+=2
        elif b == 0xE8:
            r = data[i+1]; r = r if r<128 else r-256
            ops.append((addr, f'ADD SP, {r:+d}')); i+=2
        elif b == 0xF8:
            r = data[i+1]; r = r if r<128 else r-256
            ops.append((addr, f'LD HL, SP{r:+d}')); i+=2
        elif b == 0xF5: ops.append((addr, 'PUSH AF')); i+=1
        elif b == 0xC5: ops.append((addr, 'PUSH BC')); i+=1
        elif b == 0xD5: ops.append((addr, 'PUSH DE')); i+=1
        elif b == 0xE5: ops.append((addr, 'PUSH HL')); i+=1
        elif b == 0xF1: ops.append((addr, 'POP AF')); i+=1
        elif b == 0xC1: ops.append((addr, 'POP BC')); i+=1
        elif b == 0xD1: ops.append((addr, 'POP DE')); i+=1
        elif b == 0xE1: ops.append((addr, 'POP HL')); i+=1
        elif b == 0xC9: ops.append((addr, 'RET')); i+=1
        elif b == 0xD9: ops.append((addr, 'RETI')); i+=1
        elif b == 0xC8: ops.append((addr, 'RET Z')); i+=1
        elif b == 0xC0: ops.append((addr, 'RET NZ')); i+=1
        elif b == 0xD8: ops.append((addr, 'RET C')); i+=1
        elif b == 0xD0: ops.append((addr, 'RET NC')); i+=1
        elif b == 0xE9: ops.append((addr, 'JP HL')); i+=1
        elif b == 0xAF: ops.append((addr, 'XOR A')); i+=1
        elif b == 0xA7: ops.append((addr, 'AND A')); i+=1
        elif b == 0xB7: ops.append((addr, 'OR A')); i+=1
        elif b == 0x47: ops.append((addr, 'LD B, A')); i+=1
        elif b == 0x4F: ops.append((addr, 'LD C, A')); i+=1
        elif b == 0x57: ops.append((addr, 'LD D, A')); i+=1
        elif b == 0x5F: ops.append((addr, 'LD E, A')); i+=1
        elif b == 0x67: ops.append((addr, 'LD H, A')); i+=1
        elif b == 0x6F: ops.append((addr, 'LD L, A')); i+=1
        elif b == 0x78: ops.append((addr, 'LD A, B')); i+=1
        elif b == 0x79: ops.append((addr, 'LD A, C')); i+=1
        elif b == 0x7A: ops.append((addr, 'LD A, D')); i+=1
        elif b == 0x7B: ops.append((addr, 'LD A, E')); i+=1
        elif b == 0x7C: ops.append((addr, 'LD A, H')); i+=1
        elif b == 0x7D: ops.append((addr, 'LD A, L')); i+=1
        elif b == 0x7E: ops.append((addr, 'LD A, (HL)')); i+=1
        elif b == 0x77: ops.append((addr, 'LD (HL), A')); i+=1
        elif b == 0x2A: ops.append((addr, 'LD A, (HL+)')); i+=1
        elif b == 0x22: ops.append((addr, 'LD (HL+), A')); i+=1
        elif b == 0x32: ops.append((addr, 'LD (HL-), A')); i+=1
        elif b == 0x3A: ops.append((addr, 'LD A, (HL-)')); i+=1
        elif b == 0x1A: ops.append((addr, 'LD A, (DE)')); i+=1
        elif b == 0x0A: ops.append((addr, 'LD A, (BC)')); i+=1
        elif b == 0x12: ops.append((addr, 'LD (DE), A')); i+=1
        elif b == 0x02: ops.append((addr, 'LD (BC), A')); i+=1
        elif b == 0xF9: ops.append((addr, 'LD SP, HL')); i+=1
        elif b == 0x23: ops.append((addr, 'INC HL')); i+=1
        elif b == 0x2B: ops.append((addr, 'DEC HL')); i+=1
        elif b == 0x03: ops.append((addr, 'INC BC')); i+=1
        elif b == 0x0B: ops.append((addr, 'DEC BC')); i+=1
        elif b == 0x13: ops.append((addr, 'INC DE')); i+=1
        elif b == 0x1B: ops.append((addr, 'DEC DE')); i+=1
        elif b == 0x33: ops.append((addr, 'INC SP')); i+=1
        elif b == 0x3B: ops.append((addr, 'DEC SP')); i+=1
        elif b == 0x04: ops.append((addr, 'INC B')); i+=1
        elif b == 0x05: ops.append((addr, 'DEC B')); i+=1
        elif b == 0x0C: ops.append((addr, 'INC C')); i+=1
        elif b == 0x0D: ops.append((addr, 'DEC C')); i+=1
        elif b == 0x14: ops.append((addr, 'INC D')); i+=1
        elif b == 0x15: ops.append((addr, 'DEC D')); i+=1
        elif b == 0x1C: ops.append((addr, 'INC E')); i+=1
        elif b == 0x1D: ops.append((addr, 'DEC E')); i+=1
        elif b == 0x24: ops.append((addr, 'INC H')); i+=1
        elif b == 0x25: ops.append((addr, 'DEC H')); i+=1
        elif b == 0x2C: ops.append((addr, 'INC L')); i+=1
        elif b == 0x2D: ops.append((addr, 'DEC L')); i+=1
        elif b == 0x3C: ops.append((addr, 'INC A')); i+=1
        elif b == 0x3D: ops.append((addr, 'DEC A')); i+=1
        elif b == 0x09: ops.append((addr, 'ADD HL, BC')); i+=1
        elif b == 0x19: ops.append((addr, 'ADD HL, DE')); i+=1
        elif b == 0x29: ops.append((addr, 'ADD HL, HL')); i+=1
        elif b == 0x39: ops.append((addr, 'ADD HL, SP')); i+=1
        elif b in range(0x80,0x88): ops.append((addr, f'ADD A, {["B","C","D","E","H","L","(HL)","A"][b&7]}')); i+=1
        elif b in range(0x88,0x90): ops.append((addr, f'ADC A, {["B","C","D","E","H","L","(HL)","A"][b&7]}')); i+=1
        elif b in range(0x90,0x98): ops.append((addr, f'SUB {["B","C","D","E","H","L","(HL)","A"][b&7]}')); i+=1
        elif b in range(0x98,0xA0): ops.append((addr, f'SBC A, {["B","C","D","E","H","L","(HL)","A"][b&7]}')); i+=1
        elif b in range(0xA0,0xA8): ops.append((addr, f'AND {["B","C","D","E","H","L","(HL)","A"][b&7]}')); i+=1
        elif b in range(0xA8,0xB0): ops.append((addr, f'XOR {["B","C","D","E","H","L","(HL)","A"][b&7]}')); i+=1
        elif b in range(0xB0,0xB8): ops.append((addr, f'OR {["B","C","D","E","H","L","(HL)","A"][b&7]}')); i+=1
        elif b in range(0xB8,0xC0): ops.append((addr, f'CP {["B","C","D","E","H","L","(HL)","A"][b&7]}')); i+=1
        elif b == 0x00: ops.append((addr, 'NOP')); i+=1
        elif b == 0x76: ops.append((addr, 'HALT')); i+=1
        elif b == 0xF3: ops.append((addr, 'DI')); i+=1
        elif b == 0xFB: ops.append((addr, 'EI')); i+=1
        elif b == 0x07: ops.append((addr, 'RLCA')); i+=1
        elif b == 0x0F: ops.append((addr, 'RRCA')); i+=1
        elif b == 0x17: ops.append((addr, 'RLA')); i+=1
        elif b == 0x1F: ops.append((addr, 'RRA')); i+=1
        elif b == 0x27: ops.append((addr, 'DAA')); i+=1
        elif b == 0x2F: ops.append((addr, 'CPL')); i+=1
        elif b == 0xE9: ops.append((addr, 'JP HL')); i+=1
        elif b == 0x7F: ops.append((addr, 'LD A, A')); i+=1
        elif b in range(0x40,0x80):
            regs = ['B','C','D','E','H','L','(HL)','A']
            dst = regs[(b-0x40)>>3]; src = regs[b&7]
            ops.append((addr, f'LD {dst}, {src}')); i+=1
        elif b == 0xCB:
            b2b = data[i+1]
            regs = ['B','C','D','E','H','L','(HL)','A']
            reg = regs[b2b & 7]; bit = (b2b >> 3) & 7
            hi = b2b >> 6
            rotate_ops = ['RLC','RRC','RL','RR','SLA','SRA','SWAP','SRL']
            if hi == 0: mn = f'{rotate_ops[bit]} {reg}'
            elif hi == 1: mn = f'BIT {bit}, {reg}'
            elif hi == 2: mn = f'RES {bit}, {reg}'
            else: mn = f'SET {bit}, {reg}'
            ops.append((addr, mn)); i+=2
        elif b in (0xD3,0xDB,0xDD,0xE3,0xE4,0xEB,0xEC,0xED,0xF4,0xFC,0xFD,0x10):
            ops.append((addr, f'STOP/ILL ${b:02X}')); i+=1
        else:
            ops.append((addr, f'.db ${b:02X}')); i+=1
    return ops

if __name__ == '__main__':
    gbs_path = sys.argv[1] if len(sys.argv) > 1 else 'CGB-BYTE-USA.gbs'
    target = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x3B70
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 80

    with open(gbs_path, 'rb') as f:
        raw = f.read()
    h = struct.unpack_from('<BBBHHHHBB', raw, 3)
    _ver, _num, _first, load, init, play, stack, tmod, tctl = h
    payload = bytearray(raw[0x70:])
    b0_len = 0x4000 - load  # bytes of payload placed in bank 0

    # Build a flat ROM-like image for easy address→offset mapping
    # Bank 0 occupies 0x0000..0x3FFF; payload starts at load
    # Bank 1+ occupies 0x4000..
    # Address to payload offset:
    def addr_to_off(a):
        if load <= a < 0x4000:
            return a - load
        elif 0x4000 <= a < 0x8000:
            return b0_len + (a - 0x4000)
        return None

    # data_base for dis(): we pass payload starting at load as base
    # But payload[0] == load, so base = load
    off = addr_to_off(target)
    if off is None:
        print(f'Address ${target:04X} not mappable'); sys.exit(1)

    ops = dis(payload, load, target, n)
    for a, mn in ops:
        print(f'  {a:04X}  {mn}')
