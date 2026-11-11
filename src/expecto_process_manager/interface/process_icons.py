"""Native executable icons, extracted off the GUI thread and cached by name."""
import platform
from contextlib import nullcontext
import psutil
from PySide6.QtCore import QObject
from PySide6.QtGui import QImage,QPixmap,QIcon


def extract_icons(rows,token):
    if platform.system()!='Windows': return {}
    import ctypes
    from ctypes import wintypes
    class SHFILEINFO(ctypes.Structure):
        _fields_=[('hIcon',wintypes.HICON),('iIcon',ctypes.c_int),('dwAttributes',wintypes.DWORD),
                  ('szDisplayName',wintypes.WCHAR*260),('szTypeName',wintypes.WCHAR*80)]
    shell=ctypes.WinDLL('shell32',use_last_error=True)
    shell.SHGetFileInfoW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,ctypes.POINTER(SHFILEINFO),wintypes.UINT,wintypes.UINT]
    shell.SHGetFileInfoW.restype=ctypes.c_size_t
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.DestroyIcon.argtypes=[wintypes.HICON]
    result={}
    for row in rows:
        token.check()
        try:
            process=psutil.Process(row['pid'])
            if process.create_time()!=row['created']: continue
            path=process.exe()
            info=SHFILEINFO()
            if shell.SHGetFileInfoW(path,0,ctypes.byref(info),ctypes.sizeof(info),0x100) and info.hIcon:
                try:
                    image=QImage.fromHICON(int(info.hIcon)).copy()
                    if not image.isNull(): result[row['name']]=image
                finally:
                    user.DestroyIcon(info.hIcon)
        except (psutil.Error,OSError,ValueError):
            continue
    return result


class ProcessIcons(QObject):
    def __init__(self,model,tasks,parent=None,trace=None):
        super().__init__(parent)
        self.model,self.tasks=model,tasks
        self.known=set()
        self.busy=False
        self.trace=trace

    def request(self,rows):
        if self.busy or len(self.known)>=256: return
        pending=[]
        names=set()
        for row in rows:
            if row['name'] not in self.known and row['name'] not in names:
                pending.append(dict(row))
                names.add(row['name'])
                if len(pending)>=16: break
        if not pending: return
        self.known.update(names)
        if platform.system()!='Windows':
            changed=set()
            for name in names:
                native=QIcon.fromTheme(name.removesuffix('.exe').lower())
                if not native.isNull():
                    self.model.icons[name]=native
                    changed.add(name)
            self.model.notify_icons(changed)
            return
        self.busy=True
        self.tasks.start(lambda token:extract_icons(pending,token),self.loaded,self.failed)

    def loaded(self,images):
        with self.trace.measure('icon_apply') if self.trace is not None else nullcontext():
            self.busy=False
            for name,image in images.items():
                self.model.icons[name]=QIcon(QPixmap.fromImage(image))
            self.model.notify_icons(set(images))

    def failed(self,message):
        self.busy=False
