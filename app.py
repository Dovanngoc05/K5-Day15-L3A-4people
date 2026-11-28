"""Local web entry point. Run `python app.py init-admin`, then `python run.py`."""
import argparse
import getpass
import os
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description="4people · Excel + CP-SAT scheduling")
    parser.add_argument("command",nargs="?",choices=["serve","init-admin","demo-workbooks"],default="serve")
    parser.add_argument("--username",default="admin")
    parser.add_argument("--port",type=int,default=8000)
    parser.add_argument("--data-dir",type=Path,help="Kho Excel local riêng, ví dụ runtime/demo-ready")
    args=parser.parse_args()
    from codebase.scheduler.web import create_app, add_account
    from codebase.scheduler.excel import SCHEMA, atomic_write
    app=create_app(args.data_dir)
    store=app.config["STORE"]
    if args.command=="init-admin":
        password=getpass.getpass("Mat khau admin (it nhat 12 ky tu): ")
        confirmation=getpass.getpass("Nhap lai mat khau: ")
        if password!=confirmation:
            parser.error("Mat khau khong khop")
        try:
            with store.lock:
                add_account(store,args.username,password,"admin","", "local-setup")
        except ValueError as exc:
            parser.error(str(exc))
        print("Da tao tai khoan admin. Chay: python run.py")
        return
    if args.command=="demo-workbooks":
        from codebase.scheduler.demo import demo_data
        data=demo_data()
        folder=store.root/"demo-inputs"
        for filename,tables in [("people.xlsx",["People","Enrollments","Availability"]),
                                 ("sessions.xlsx",["Sessions","Slots","Weights"]),("rooms.xlsx",["Rooms"])]:
            atomic_write(folder/filename,{k:data[k] for k in tables},SCHEMA)
        print("Du lieu hoan toan gia lap: "+str(folder.resolve()))
        return
    from waitress import serve
    print(f"4people · http://127.0.0.1:{args.port}",flush=True)
    serve(app,host="127.0.0.1",port=args.port,threads=4)


if __name__=="__main__":
    main()
