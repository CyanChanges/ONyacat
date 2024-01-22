#  Copyright (c) Cyan Changes 2024. All rights reserved.

from argparse import ArgumentParser
from server_udp.serve import main
from rich.traceback import install

install()

parser = ArgumentParser("Onlyacat Server", add_help=False)

parser.add_argument("-h", "--host", help="Host to listen on", default="0.0.0.0")
parser.add_argument("-p", "--port", type=int, default=5100, help="Port to listen on")

args = parser.parse_args()
main(args.host, args.port)
