# SlugTPU: A Simple Neural Network Accelerator ASIC

# Setup
## Simulation
1. Download OSS CAD Suite [**2026-01-27](https://github.com/YosysHQ/oss-cad-suite-build/releases/tag/2026-01-27) build** from YosysHQ
2. Source into OSS Cad Suite environment
```
source $YOUR_OSS_CAD_INSTALL_DIRECTORY/oss_cad_suite/environment
```
3. Install Pytest
```
pip3 install -U pytest
```
You may also need to recompile CocoTB, such as on a ARM Mac.
```
python3 -m pip install --force-reinstall --no-binary cocotb cocotb
```
4. Ensure the current working directory is in this projects top level directory (i.e. at ~/slugtpu, not ~/slugtpu/sim, etc.). The Makefile uses relative paths to keep things simple.
5. Make!
```
# Test fifo
make test_fifo
```

