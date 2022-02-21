from dataclasses import dataclass

@dataclass
class KermitVariable:
    name: str
    size: str
    vtype: str
    crc: str # Kermit returns an integer for this, but we convert it to a hexstring
    
    
