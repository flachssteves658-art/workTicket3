import sys
import zipfile


def main():
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "-Z1":
        with zipfile.ZipFile(args[1]) as archive:
            sys.stdout.buffer.write(("\n".join(archive.namelist()) + "\n").encode("utf-8"))
        return
    if len(args) == 3 and args[0] == "-p":
        with zipfile.ZipFile(args[1]) as archive:
            sys.stdout.buffer.write(archive.read(args[2]))
        return
    raise SystemExit("Supported usage: unzip -Z1 ZIP | unzip -p ZIP ENTRY")


if __name__ == "__main__":
    main()
