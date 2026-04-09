#!/usr/bin/env python
from __future__ import annotations

import glob
import multiprocessing.pool
import os
from pathlib import Path
import shutil
import tarfile
from typing import Any
import urllib.request
import warnings

from setuptools import distutils, find_packages, setup

try:
    from torch.utils.cpp_extension import BuildExtension, CppExtension, include_paths
except ModuleNotFoundError as error:
    raise ModuleNotFoundError(
        "PyTorch is required to build ctcdecode. Install torch in the target "
        "environment first, then retry with `pip install . --no-build-isolation` "
        "when using modern pip."
    ) from error


REPO_ROOT = Path(__file__).resolve().parent
THIRD_PARTY_DIR = REPO_ROOT / "third_party"
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "ctcdecode"
CACHE_DIR = Path(os.environ.get("CTCDECODE_CACHE_DIR", str(DEFAULT_CACHE_DIR))).expanduser()
DOWNLOAD_TIMEOUT = float(os.environ.get("CTCDECODE_DOWNLOAD_TIMEOUT", "30"))
THIRD_PARTY_ARCHIVES = {
    "openfst-1.6.7.tar.gz": "https://github.com/parlance/ctcdecode/releases/download/v1.0/openfst-1.6.7.tar.gz",
    "boost_1_67_0.tar.gz": "https://github.com/parlance/ctcdecode/releases/download/v1.0/boost_1_67_0.tar.gz",
}
THIRD_PARTY_LIBS = ["kenlm", "openfst-1.6.7/src/include", "ThreadPool", "boost_1_67_0", "utf8"]


def is_truthy(value: str | None) -> bool:
    """判断环境变量是否表示启用状态。"""
    return value is not None and value.strip().lower() in {"1", "true", "yes", "on"}


def archive_extract_dir(archive_name: str) -> Path:
    """根据压缩包名返回解压后的目录路径。"""
    if not archive_name.endswith(".tar.gz"):
        raise ValueError(f"Unsupported archive format: {archive_name}")
    return THIRD_PARTY_DIR / archive_name[: -len(".tar.gz")]


def download_archive(url: str, destination: Path) -> None:
    """下载第三方压缩包到本地缓存目录。"""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT) as response:
        with destination.open("wb") as output_file:
            shutil.copyfileobj(response, output_file)


def extract_archive(archive_path: Path) -> None:
    """将第三方压缩包解压到仓库的 third_party 目录。"""
    extract_dir = archive_extract_dir(archive_path.name)
    if extract_dir.is_dir():
        return
    with tarfile.open(archive_path) as tar_file:
        tar_file.extractall(THIRD_PARTY_DIR)


def ensure_archive_available(archive_name: str, url: str) -> None:
    """优先使用本地仓库和用户缓存中的压缩包，必要时再联网下载。"""
    extract_dir = archive_extract_dir(archive_name)
    local_archive = THIRD_PARTY_DIR / archive_name
    cached_archive = CACHE_DIR / archive_name
    offline_mode = is_truthy(os.environ.get("CTCDECODE_OFFLINE"))

    if extract_dir.is_dir():
        return

    if local_archive.is_file():
        extract_archive(local_archive)
        return

    if cached_archive.is_file():
        THIRD_PARTY_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cached_archive, local_archive)
        extract_archive(local_archive)
        return

    if offline_mode:
        raise RuntimeError(
            "Offline mode is enabled and the required archive is missing. "
            f"Expected `{local_archive}` or `{cached_archive}`. "
            f"Download it from `{url}` on a machine with internet access first."
        )

    download_archive(url, cached_archive)
    THIRD_PARTY_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cached_archive, local_archive)
    extract_archive(local_archive)


def ensure_third_party_archives() -> None:
    """确保构建扩展时依赖的第三方源码已就绪。"""
    for archive_name, url in THIRD_PARTY_ARCHIVES.items():
        ensure_archive_available(archive_name, url)


def collect_third_party_sources() -> list[str]:
    """收集第三方库的 C/C++ 源文件列表。"""
    lib_sources = (
        glob.glob(str(THIRD_PARTY_DIR / "kenlm" / "util" / "*.cc"))
        + glob.glob(str(THIRD_PARTY_DIR / "kenlm" / "lm" / "*.cc"))
        + glob.glob(str(THIRD_PARTY_DIR / "kenlm" / "util" / "double-conversion" / "*.cc"))
        + glob.glob(str(THIRD_PARTY_DIR / "openfst-1.6.7" / "src" / "lib" / "*.cc"))
    )
    return [source for source in lib_sources if not (source.endswith("main.cc") or source.endswith("test.cc"))]


def collect_third_party_includes() -> list[str]:
    """收集第三方库的头文件目录。"""
    return [str((THIRD_PARTY_DIR / library).resolve()) for library in THIRD_PARTY_LIBS]


for file in ["third_party/kenlm/setup.py", "third_party/ThreadPool/ThreadPool.h"]:
    if not os.path.exists(file):
        warnings.warn("File `{}` does not appear to be present. Did you forget `git submodule update`?".format(file))


# Does gcc compile with this header and library?
def compile_test(header: str, library: str) -> bool:
    """检测当前编译器是否支持给定头文件和系统库。"""
    dummy_path = os.path.join(os.path.dirname(__file__), "dummy")
    command = (
        'bash -c "g++ -include '
        + header
        + " -l"
        + library
        + " -x c++ - <<<'int main() {}' -o "
        + dummy_path
        + " >/dev/null 2>/dev/null && rm "
        + dummy_path
        + ' 2>/dev/null"'
    )
    return os.system(command) == 0


compile_args = ["-O3", "-DKENLM_MAX_ORDER=6", "-std=c++17", "-fPIC"]
ext_libs = []
if compile_test("zlib.h", "z"):
    compile_args.append("-DHAVE_ZLIB")
    ext_libs.append("z")

if compile_test("bzlib.h", "bz2"):
    compile_args.append("-DHAVE_BZLIB")
    ext_libs.append("bz2")

if compile_test("lzma.h", "lzma"):
    compile_args.append("-DHAVE_XZLIB")
    ext_libs.append("lzma")

compile_args.extend(["-DINCLUDE_KENLM", "-DKENLM_MAX_ORDER=6"])
ctc_sources = glob.glob(str(REPO_ROOT / "ctcdecode" / "src" / "*.cpp"))

extension = CppExtension(
    name="ctcdecode._ext.ctc_decode",
    package=True,
    with_cuda=False,
    sources=ctc_sources,
    include_dirs=include_paths(),
    libraries=ext_libs,
    extra_compile_args=compile_args,
    language="c++",
)


class CtcDecodeBuildExtension(BuildExtension):
    """在真正编译扩展前准备第三方源码，避免 metadata 阶段触发网络访问。"""

    def run(self) -> None:
        """强制在当前环境重新构建扩展，避免复用其他机器遗留的二进制产物。"""
        self.force = True
        super().run()

    def build_extensions(self) -> None:
        """补齐第三方源码和头文件目录后再调用父类编译逻辑。"""
        ensure_third_party_archives()
        third_party_sources = collect_third_party_sources()
        third_party_includes = collect_third_party_includes()

        for build_extension in self.extensions:
            for source in third_party_sources:
                if source not in build_extension.sources:
                    build_extension.sources.append(source)
            for include_dir in third_party_includes:
                if include_dir not in build_extension.include_dirs:
                    build_extension.include_dirs.append(include_dir)

        super().build_extensions()


# monkey-patch for parallel compilation
# See: https://stackoverflow.com/a/13176803
def parallel_c_compile(
    self: Any,
    sources: list[str],
    output_dir: str | None = None,
    macros: Any = None,
    include_dirs: Any = None,
    debug: int = 0,
    extra_preargs: Any = None,
    extra_postargs: Any = None,
    depends: Any = None,
) -> list[str]:
    """使用线程池并行编译对象文件。"""
    # those lines are copied from distutils.ccompiler.CCompiler directly
    macros, objects, extra_postargs, pp_opts, build = self._setup_compile(
        output_dir, macros, include_dirs, sources, depends, extra_postargs
    )
    cc_args = self._get_cc_args(pp_opts, debug, extra_preargs)

    # parallel code
    def _single_compile(obj: str) -> None:
        """编译单个目标文件。"""
        try:
            src, ext = build[obj]
        except KeyError:
            return
        self._compile(obj, src, ext, cc_args, extra_postargs, pp_opts)

    # convert to list, imap is evaluated on-demand
    thread_pool = multiprocessing.pool.ThreadPool(os.cpu_count())
    list(thread_pool.imap(_single_compile, objects))
    return objects


# hack compile to support parallel compiling
distutils.ccompiler.CCompiler.compile = parallel_c_compile

setup(
    name="ctcdecode",
    version="1.0.3",
    description="CTC Decoder for PyTorch based on Paddle Paddle's implementation",
    url="https://github.com/parlance/ctcdecode",
    author="Ryan Leary",
    author_email="ryanleary@gmail.com",
    # Exclude the build files.
    packages=find_packages(exclude=["build"]),
    ext_modules=[extension],
    cmdclass={"build_ext": CtcDecodeBuildExtension},
)
