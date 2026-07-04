data=open("web_app.py","rb").read()
if b"_gap_seed_diag" in data:
    print("already patched"); raise SystemExit(0)
new=open("new_gap_seed_diag.py","rb").read().replace(b"\r\n",b"\n").replace(b"\n",b"\r\n")
T=b'if __name__ == "__main__":'
pos=data.rfind(T)
data=data[:pos]+new+b"\r\n\r\n"+data[pos:]
open("web_app.py","wb").write(data)
print("diag route patched")
