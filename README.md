# pyproot

**pyproot**, proot'u Python üzerinden kullanmanızı sağlayan, proot binary'sini kendi içinde taşıyan bir Python kütüphanesidir.

[proot](https://proot-me.github.io/) — root yetkisi gerektirmeden `chroot`, bind-mount ve yabancı mimari emülasyonu yapmanızı sağlayan bir araçtır.

---

## Özellikler

- 🔌 **Gömülü binary** — proot'u ayrıca kurmanıza gerek yok; wheel içinde statik binariler gelir.
- 🏗️ **Builder API** — metotlar `self` döndürür, zincir halinde kullanılabilir.
- 🐍 **Saf Python** — runtime bağımlılığı yok, yalnızca standart kütüphane.
- 🌍 **Çoklu mimari** — x86_64, aarch64, armv7l, i386.
- 🔄 **Otomatik indirme** — binary bulunamazsa `~/.cache/pyproot/` altına indirir.
- 🖥️ **CLI** — `pyproot` komutu ile terminalden de kullanılabilir.

---

## Kurulum

```bash
pip install pyproot
```

Wheel içinde proot binary'si gömülüdür; ek kurulum gerekmez.

---

## Hızlı Başlangıç

### Tek komut çalıştırma

```python
import pyproot

result = pyproot.run(
    ["/bin/sh", "-c", "uname -a"],
    rootfs="/opt/alpine",
    binds=["/proc", "/sys", "/dev"],
)
print(result.stdout)
```

### PRoot sınıfı — builder stili

```python
from pyproot import PRoot

result = (
    PRoot(rootfs="/opt/alpine")
    .bind("/proc", "/proc")
    .bind("/sys",  "/sys")
    .bind("/dev",  "/dev")
    .env("TERM", "xterm-256color")
    .workdir("/root")
    .run(["/bin/sh", "-c", "cat /etc/os-release"])
)
print(result.stdout)
```

### Context manager

```python
from pyproot import PRoot

with PRoot(rootfs="/opt/ubuntu") as pr:
    pr.bind("/proc").bind("/sys").bind("/dev")
    result = pr.run(["/bin/bash", "-c", "apt list --installed 2>/dev/null | head -5"])
    print(result.stdout)
```

### Streaming / interaktif süreç

```python
import subprocess
from pyproot import PRoot

pr = PRoot(rootfs="/opt/alpine")
pr.bind("/proc").bind("/sys")

proc = pr.popen(
    ["/bin/sh"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)
stdout, stderr = proc.communicate(input="echo hello from proot\nexit\n")
print(stdout)
```

### Yabancı mimari emülasyonu (QEMU)

```python
from pyproot import PRoot

# ARM rootfs'ini x86_64 makine üzerinde çalıştırma
pr = PRoot(
    rootfs="/opt/arm-rootfs",
    qemu="qemu-arm",
)
pr.bind("/proc").bind("/sys")
result = pr.run(["/bin/uname", "-m"])
print(result.stdout)  # armv7l
```

### Hata yakalama

```python
from pyproot import PRoot, ProotExecutionError

pr = PRoot(rootfs="/opt/alpine")
try:
    pr.run(["/bin/sh", "-c", "exit 42"], check=True)
except ProotExecutionError as e:
    print(f"Komut başarısız: {e}")
    print(f"Çıkış kodu: {e.returncode}")
```

---

## CLI

```bash
# Bilgi göster
pyproot --info

# Komut çalıştır
pyproot --rootfs /opt/alpine -- /bin/sh -c "uname -a"

# Bind mount ile
pyproot --rootfs /opt/alpine --bind /proc --bind /sys -- /bin/bash

# proot binary'sini indir
pyproot --download x86_64
```

---

## API Referansı

### `pyproot.run(command, *, rootfs, binds, cwd, env, qemu, timeout, capture_output)`

Tek seferlik kullanım için kolaylık fonksiyonu. `subprocess.CompletedProcess` döndürür.

### `PRoot(rootfs, *, cwd, qemu, proot_binary, mix_rootfs, kill_on_exit, link2symlink, no_seccomp, verbose)`

Ana sınıf. Tüm metodlar `self` döndürür (zincir kullanımı için).

| Metot | Açıklama |
|---|---|
| `.bind(host, guest=None)` | Bind mount ekle |
| `.env(key, value)` | Ortam değişkeni ekle |
| `.workdir(path)` | Guest içi çalışma dizini |
| `.use_qemu(binary)` | QEMU emülasyonu |
| `.run(command, ...)` | Komutu çalıştır → `CompletedProcess` |
| `.popen(command, ...)` | Süreç başlat → `Popen` |
| `.build_argv(command)` | Tam komut satırını döndür (debug için) |
| `.version()` | proot binary versiyonunu döndür |

### `pyproot.get_proot_binary(prefer_system=False)`

Kullanılacak proot binary yolunu döndürür.

Çözüm sırası:
1. `PYPROOT_BINARY` ortam değişkeni
2. Pakete gömülü binary (`pyproot/binaries/proot-<arch>`)
3. Sistem PATH'indeki proot
4. `~/.cache/pyproot/` altındaki önbellek
5. Otomatik indirme

### `pyproot.download_proot(dest_dir=None, force=False)`

Geçerli mimari için proot binary'sini indirir.

---

## Binary'leri Kendiniz Derlemek / Güncellemek

```bash
# Tüm mimariler için indir
python scripts/download_binaries.py

# Yalnızca x86_64
python scripts/download_binaries.py x86_64

# Mevcut binary'leri kontrol et
python scripts/download_binaries.py --check
```

---

## Geliştirme

```bash
git clone https://github.com/yourname/pyproot
cd pyproot
pip install -e ".[dev]"

# Unit testleri çalıştır (proot gerekmez)
pytest tests/

# Entegrasyon testlerini çalıştır (proot gerekir)
pytest tests/ -m integration
```

---

## Lisans

MIT

---

## proot Hakkında

proot, Linux çekirdeğinin `ptrace` mekanizmasını kullanarak kullanıcı alanında çalışır; `root` yetkisi gerektirmez.
Daha fazla bilgi için: https://proot-me.github.io/
