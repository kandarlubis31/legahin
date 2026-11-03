# legahin — Project Context

## Ringkasan

CLI untuk memeriksa dan merapikan penyimpanan: memindai folder, menghitung ukuran, mendeteksi berkas
duplikat, lalu meminta model AI menyusun rencana pembersihan yang bisa ditinjau sebelum dijalankan.

## Alur

```
scan folder → daftar berkas (ukuran, tanggal akses, hash)
                    ↓
   ringkasan: total, sisa disk, duplikat, berkas besar, berkas lama, tipe terbesar,
              100 berkas terbesar (nama + path + ukuran)
                    ↓
   model (OpenRouter, default openai/gpt-4o-mini)
                    ↓
   rekomendasi → konfirmasi mengetik "yes" → eksekusi
```

Yang dikirim ke model hanya ringkasan metadata di atas — **isi berkas tidak pernah dikirim**.
Sebaliknya, nama dan path ikut terkirim supaya sarannya konkret ("hapus `node_modules` di proyek X"),
bukan saran umum.

Penghapusan baru berjalan setelah pengguna mengetik `yes`; tanpa itu, hanya rencana yang ditampilkan.

Duplikat dicari lewat hash isi (bukan nama), sehingga berkas yang diganti nama tetap terdeteksi.

## Konfigurasi

```
OPENROUTER_API_KEY=sk-or-...           wajib
OPENROUTER_MODEL=openai/gpt-4o-mini    opsional
```

## Menjalankan

```bash
pip install openai
export OPENROUTER_API_KEY='sk-or-...'
python cleaner.py --help
```

## Struktur

```
cleaner.py   Seluruh CLI: pemindaian, hashing, ringkasan, pemanggilan AI, eksekusi
.env         Kunci API (tidak di-commit)
```

## Catatan

- Coba dulu pada folder percobaan; hentikan sebelum konfirmasi untuk melihat rencananya saja.
- Hashing berkas besar memakan waktu — pindai per subfolder daripada seluruh drive sekaligus.
- Path berkas ikut terkirim ke penyedia model; jangan jalankan pada folder yang namanya sensitif.
