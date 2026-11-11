"""Encode the supplied PNG as a Windows ICO with multiple native sizes."""
from pathlib import Path
import struct
from PySide6.QtCore import QBuffer,QByteArray,QIODevice,Qt
from PySide6.QtGui import QImage


def build_icon():
    assets=Path(__file__).resolve().parents[1]/'src/expecto_process_manager/interface/assets'
    original=QImage(str(assets/'expecto.png'))
    if original.isNull(): raise ValueError('A imagem original do ícone não foi encontrada.')
    entries=[]
    for size in (16,24,32,48,64,128,256):
        image=original.scaled(size,size,Qt.KeepAspectRatio,Qt.SmoothTransformation)
        data=QByteArray(); buffer=QBuffer(data); buffer.open(QIODevice.WriteOnly)
        if not image.save(buffer,'PNG'): raise ValueError('Não foi possível codificar o ícone.')
        entries.append((size,bytes(data)))
    offset=6+16*len(entries)
    header=struct.pack('<HHH',0,1,len(entries))
    images=[]
    for size,data in entries:
        header+=struct.pack('<BBBBHHII',size if size<256 else 0,size if size<256 else 0,0,0,1,32,len(data),offset)
        images.append(data); offset+=len(data)
    target=assets/'expecto.ico'; target.write_bytes(header+b''.join(images))
    return target


if __name__=='__main__': print(build_icon())
