# ctcdecode 中文安装说明

本文档说明如何在以下 PyTorch 环境上安装当前仓库中的 `ctcdecode`：

```bash
pip install torch==2.7.0 torchvision==0.22.0 torchaudio==2.7.0 --index-url https://download.pytorch.org/whl/cu128
```

## 1. 环境要求

- Python 3.11 或兼容版本
- Linux
- `g++` 或 `clang++`
- `git`
- 已经可以正常安装并导入 `torch==2.7.0+cu128`

建议使用独立虚拟环境或 Conda 环境。

## 2. 安装 PyTorch 2.7.0 + CUDA 12.8

如果你还没有创建环境，可以参考下面的方式：

```bash
conda create -n CSLR python=3.11 -y
conda activate CSLR
```

安装 PyTorch：

```bash
pip install torch==2.7.0 torchvision==0.22.0 torchaudio==2.7.0 --index-url https://download.pytorch.org/whl/cu128
```

确认安装成功：

```bash
python - <<'PY'
import torch
print(torch.__version__)
print(torch.version.cuda)
PY
```

预期至少应该看到：

```text
2.7.0+cu128
12.8
```

## 3. 获取 ctcdecode 源码

必须带上 `--recursive`，因为仓库依赖 `third_party` 里的子模块和第三方代码。

```bash
git clone --recursive https://github.com/WayenVan/ctcdecode.git
cd ctcdecode
```

如果你已经克隆过仓库但没有带 `--recursive`，补一次即可：

```bash
git submodule update --init --recursive
```

## 4. 安装 ctcdecode

在已经安装好 PyTorch 的同一个环境里执行：

```bash
pip install . --no-build-isolation
```

不要直接使用下面这条命令：

```bash
pip install .
```

离线安装
```bash
CTCDECODE_OFFLINE=1 pip install . --no-build-isolation
```

原因是当前仓库的 [setup.py](setup.py) 在构建阶段会直接导入 `torch.utils.cpp_extension`。
新版本 `pip` 默认使用隔离构建环境，隔离环境看不到你当前环境里已经安装好的 PyTorch，于是会报错：

```text
ModuleNotFoundError: No module named 'torch'
```

`--no-build-isolation` 的作用是让构建过程直接复用你当前环境里的 `torch`。

## 5. 验证安装

安装完成后，先验证导入：

```bash
python - <<'PY'
import ctcdecode
print(ctcdecode.__file__)
PY
```

如果你希望进一步验证功能，可以运行仓库自带测试：

```bash
python tests/test_decode.py
```

## 6. 一条命令版

如果你的环境已经激活，并且 PyTorch 已经按上面的版本装好，那么完整流程是：

```bash
pip install torch==2.7.0 torchvision==0.22.0 torchaudio==2.7.0 --index-url https://download.pytorch.org/whl/cu128
git clone --recursive https://github.com/WayenVan/ctcdecode.git
cd ctcdecode
pip install . --no-build-isolation
python tests/test_decode.py
```

## 7. 常见问题

### 7.1 `ModuleNotFoundError: No module named 'torch'`

说明你用了：

```bash
pip install .
```

请改成：

```bash
pip install . --no-build-isolation
```

并确认当前执行 `pip` 的环境与安装 `torch` 的环境一致。

### 7.2 子模块或第三方文件缺失

如果报错提示 `third_party/kenlm/setup.py` 或 `third_party/ThreadPool/ThreadPool.h` 不存在，请执行：

```bash
git submodule update --init --recursive
```

### 7.3 编译器缺失

如果报 `g++: command not found` 或类似错误，需要先安装系统编译工具链。

## 8. 本仓库上的实际验证结果

在本机以下环境中，已经验证通过：

- Python: `3.11`
- PyTorch: `2.7.0+cu128`
- CUDA runtime tag: `12.8`
- 安装命令: `pip install . --no-build-isolation`
- 验证命令: `python tests/test_decode.py`

本机一次实际输出为：

```text
Ran 10 tests in 3.570s

OK
```
