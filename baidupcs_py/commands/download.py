from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import os
import shutil
import subprocess
import time
from concurrent.futures import Future

from baidupcs_py.baidupcs import BaiduPCSApi, PCS_UA
from baidupcs_py.utils import human_size, human_size_to_int
from baidupcs_py.common import constant
from baidupcs_py.common.io import to_decryptio, DecryptIO, READ_SIZE, MAX_CHUNK_SIZE
from baidupcs_py.common.downloader import MeDownloader
from baidupcs_py.common.progress_bar import (
    _progress,
    init_progress_bar,
    progress_task_exists,
)
from baidupcs_py.commands.sifter import Sifter, sift
from baidupcs_py.commands.log import get_logger
from baidupcs_py.commands.display import display_blocked_remotepath

_print = print

from rich import print
from rich.progress import TaskID

logger = get_logger(__name__)


DEFAULT_CONCURRENCY = 5
DEFAULT_CHUNK_SIZE = str(MAX_CHUNK_SIZE)


@dataclass
class DownloadParams:
    concurrency: int = DEFAULT_CONCURRENCY
    chunk_size: str = DEFAULT_CHUNK_SIZE
    quiet: bool = False
    downloader_params: List[str] = field(default_factory=list)


DEFAULT_DOWNLOADPARAMS = DownloadParams()


class Downloader(Enum):
    me = "me"
    aget_py = "aget"  # https://github.com/PeterDing/aget
    aget_rs = "ag"  # https://github.com/PeterDing/aget-rs
    aria2 = "aria2c"  # https://github.com/aria2/aria2

    # No use axel. It Can't handle URLs of length over 1024
    # axel = 'axel'  # https://github.com/axel-download-accelerator/axel

    # No use wget. the file url of baidupan only supports `Range` request

    def which(self) -> Optional[str]:
        return shutil.which(self.value)

    def download(
        self,
        url: str,
        localpath: str,
        cookies: Dict[str, Optional[str]],
        downloadparams: DownloadParams = DEFAULT_DOWNLOADPARAMS,
        out_cmd: bool = False,
        encrypt_password: bytes = b"",
    ):
        global DEFAULT_DOWNLOADER
        if not self.which():
            self = DEFAULT_DOWNLOADER

        if self == Downloader.me:
            self._me_download(
                url,
                localpath,
                cookies=cookies,
                downloadparams=downloadparams,
                encrypt_password=encrypt_password,
            )
            return
        elif self == Downloader.aget_py:
            cmd = self._aget_py_cmd(url, localpath, cookies, downloadparams)
        elif self == Downloader.aget_rs:
            cmd = self._aget_rs_cmd(url, localpath, cookies, downloadparams)
        elif self == Downloader.aria2:
            cmd = self._aria2_cmd(url, localpath, cookies, downloadparams)
        else:
            cmd = self._aget_py_cmd(url, localpath, cookies, downloadparams)

        # Print out command
        if out_cmd:
            _print(" ".join((repr(c) for c in cmd)))
            return

        returncode = self.spawn(cmd, downloadparams.quiet)

        logger.debug("`download`: cmd returncode: %s", returncode)

        if returncode != 0:
            print(f"[italic]{self.value}[/italic] fails. return code: [red]{returncode}[/red]")

    def spawn(self, cmd: List[str], quiet: bool = False):
        child = subprocess.run(cmd, stdout=subprocess.DEVNULL if quiet else None)
        return child.returncode

    def _me_download(
        self,
        url: str,
        localpath: str,
        cookies: Dict[str, Optional[str]],
        downloadparams: DownloadParams = DEFAULT_DOWNLOADPARAMS,
        done_callback: Optional[Callable[[Future], Any]] = None,
        encrypt_password: bytes = b"",
    ):
        headers = {
            "Cookie": f"BDUSS={cookies['BDUSS']};",
            "User-Agent": PCS_UA,
            "Connection": "Keep-Alive",
        }

        task_id: Optional[TaskID] = None
        if not downloadparams.quiet:
            init_progress_bar()
            task_id = _progress.add_task("MeDownloader", start=False, title=localpath)

        def _wrap_done_callback(fut: Future):
            if task_id is not None:
                _progress.remove_task(task_id)
            if done_callback:
                done_callback(fut)

        def monit_callback(task_id: Optional[TaskID], offset: int):
            if task_id is not None:
                _progress.update(task_id, completed=offset + 1)

        def except_callback(task_id: Optional[TaskID]):
            if task_id is not None and progress_task_exists(task_id):
                _progress.reset(task_id)

        chunk_size_int = human_size_to_int(downloadparams.chunk_size)
        meDownloader = MeDownloader(
            "GET",
            url,
            headers=headers,
            max_workers=downloadparams.concurrency,
            max_chunk_size=chunk_size_int,
            callback=monit_callback,
            encrypt_password=encrypt_password,
        )

        if task_id is not None:
            length = len(meDownloader)
            _progress.update(task_id, total=length)
            _progress.start_task(task_id)

        meDownloader.download(
            Path(localpath),
            task_id=task_id,
            continue_=True,
            done_callback=_wrap_done_callback,
            except_callback=except_callback,
        )

    def _aget_py_cmd(
        self,
        url: str,
        localpath: str,
        cookies: Dict[str, Optional[str]],
        downloadparams: DownloadParams = DEFAULT_DOWNLOADPARAMS,
    ):
        _ck = f"Cookie: BDUSS={cookies['BDUSS']};"

        # This is an error of aget-py
        chunk_size = human_size_to_int(downloadparams.chunk_size)
        if chunk_size == MAX_CHUNK_SIZE:
            chunk_size -= constant.OneM

        cmd = [
            self.which(),
            url,
            "-o",
            localpath,
            "-H",
            f"User-Agent: {PCS_UA}",
            "-H",
            "Connection: Keep-Alive",
            "-H",
            _ck,
            "-s",
            str(downloadparams.concurrency),
            "-k",
            str(chunk_size),
            *downloadparams.downloader_params,
        ]
        return cmd

    def _aget_rs_cmd(
        self,
        url: str,
        localpath: str,
        cookies: Dict[str, Optional[str]],
        downloadparams: DownloadParams = DEFAULT_DOWNLOADPARAMS,
    ):
        _ck = f"Cookie: BDUSS={cookies['BDUSS']};"
        cmd = [
            self.which(),
            url,
            "-o",
            localpath,
            "-H",
            f"User-Agent: {PCS_UA}",
            "-H",
            "Connection: Keep-Alive",
            "-H",
            _ck,
            "-s",
            str(downloadparams.concurrency),
            "-k",
            downloadparams.chunk_size,
            *downloadparams.downloader_params,
        ]
        return cmd

    def _aria2_cmd(
        self,
        url: str,
        localpath: str,
        cookies: Dict[str, Optional[str]],
        downloadparams: DownloadParams = DEFAULT_DOWNLOADPARAMS,
    ):
        _ck = f"Cookie: BDUSS={cookies['BDUSS']};"
        directory, filename = os.path.split(localpath)
        cmd = [
            self.which(),
            url,
            "-c",
            "--dir",
            directory,
            "-o",
            filename,
            "--header",
            f"User-Agent: {PCS_UA}",
            "--header",
            "Connection: Keep-Alive",
            "--header",
            _ck,
            "-s",
            str(downloadparams.concurrency),
            "-k",
            downloadparams.chunk_size,
            *downloadparams.downloader_params,
        ]
        return cmd


DEFAULT_DOWNLOADER = Downloader.me


def download_file(
    api: BaiduPCSApi,
    remotepath: str,
    localdir: str,
    downloader: Downloader = DEFAULT_DOWNLOADER,
    downloadparams: DownloadParams = DEFAULT_DOWNLOADPARAMS,
    out_cmd: bool = False,
    encrypt_password: bytes = b"",
):
    localpath = Path(localdir) / os.path.basename(remotepath)

    # Make sure parent directory existed
    if not localpath.parent.exists():
        localpath.parent.mkdir(parents=True)

    if not out_cmd and localpath.exists():
        print(f"[yellow]{localpath}[/yellow] is ready existed.")
        return

    dlink = api.download_link(remotepath)
    if not dlink:
        display_blocked_remotepath(remotepath)
        return

    if downloader != Downloader.me:
        print(f"[italic blue]Download[/italic blue]: {remotepath} to {localpath}")
    downloader.download(
        dlink,
        str(localpath),
        api.cookies,
        downloadparams=downloadparams,
        out_cmd=out_cmd,
        encrypt_password=encrypt_password,
    )


def download_dir(
    api: BaiduPCSApi,
    remotedir: str,
    localdir: str,
    sifters: List[Sifter] = [],
    recursive: bool = False,
    from_index: int = 0,
    downloader: Downloader = DEFAULT_DOWNLOADER,
    downloadparams=DEFAULT_DOWNLOADPARAMS,
    out_cmd: bool = False,
    encrypt_password: bytes = b"",
):
    remotepaths = api.list(remotedir)
    remotepaths = sift(remotepaths, sifters, recursive=recursive)
    for rp in remotepaths[from_index:]:
        if rp.is_file:
            download_file(
                api,
                rp.path,
                localdir,
                downloader,
                downloadparams=downloadparams,
                out_cmd=out_cmd,
                encrypt_password=encrypt_password,
            )
        else:  # is_dir
            if recursive:
                _localdir = Path(localdir) / os.path.basename(rp.path)
                download_dir(
                    api,
                    rp.path,
                    str(_localdir),
                    sifters=sifters,
                    recursive=recursive,
                    from_index=from_index,
                    downloader=downloader,
                    downloadparams=downloadparams,
                    out_cmd=out_cmd,
                    encrypt_password=encrypt_password,
                )


def download(
    api: BaiduPCSApi,
    remotepaths: List[str],
    localdir: str,
    sifters: List[Sifter] = [],
    recursive: bool = False,
    from_index: int = 0,
    downloader: Downloader = DEFAULT_DOWNLOADER,
    downloadparams: DownloadParams = DEFAULT_DOWNLOADPARAMS,
    out_cmd: bool = False,
    encrypt_password: bytes = b"",
):
    """Download `remotepaths` to the `localdir`

    Args:
        `from_index` (int): The start index of downloading entries from EACH remote directory
    """

    logger.debug(
        "`download`: sifters: %s, recursive: %s, from_index: %s, "
        "downloader: %s, downloadparams: %s, out_cmd: %s, has encrypt_password: %s",
        sifters,
        recursive,
        from_index,
        downloader,
        downloadparams,
        out_cmd,
        bool(encrypt_password),
    )
    logger.debug(
        "`download`: remotepaths should be uniq %s == %s",
        len(remotepaths),
        len(set(remotepaths)),
    )

    # assert (
    #     human_size_to_int(downloadparams.chunk_size) <= MAX_CHUNK_SIZE
    # ), f"`chunk_size` must be less or equal then {human_size(MAX_CHUNK_SIZE)}"

    for rp in remotepaths:
        if not api.exists(rp):
            print(f"[yellow]WARNING[/yellow]: `{rp}` does not exist.")
            continue

        if api.is_file(rp):
            download_file(
                api,
                rp,
                localdir,
                downloader=downloader,
                downloadparams=downloadparams,
                out_cmd=out_cmd,
                encrypt_password=encrypt_password,
            )
        else:
            _localdir = str(Path(localdir) / os.path.basename(rp))
            download_dir(
                api,
                rp,
                _localdir,
                sifters=sifters,
                recursive=recursive,
                from_index=from_index,
                downloader=downloader,
                downloadparams=downloadparams,
                out_cmd=out_cmd,
                encrypt_password=encrypt_password,
            )

    if downloader == Downloader.me:
        MeDownloader._exit_executor()

    _progress.stop()
