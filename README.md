# legahin

CLI untuk memeriksa penyimpanan: memindai folder, menghitung ukuran, menemukan berkas duplikat, lalu
meminta model AI menyusun rencana pembersihan yang bisa kamu tinjau sebelum dieksekusi.

## Memasang

```bash
pip install openai
export OPENROUTER_API_KEY='sk-or-...'
```

Bisa juga disimpan di `.env` dalam folder yang sama:

```
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_MODEL=openai/gpt-4o-mini
```

## Menjalankan

```bash
python cleaner.py                    # pindai folder saat ini
python cleaner.py D:/Downloads       # pindai folder tertentu
python cleaner.py --no-ai            # laporan saja, tanpa memanggil model
python cleaner.py --large 500 --old 180
```

| Opsi | Arti |
| :--- | :--- |
| `path` | Folder yang dipindai (default `.`) |
| `--large <MB>` | Ambang berkas besar (default dari `LARGE_FILE_MB`) |
| `--old <hari>` | Ambang berkas lama berdasarkan tanggal akses |
| `--max <n>` | Batas jumlah berkas yang dipindai (default 10.000) |
| `--no-ai` | Lewati analisis AI |

## Yang dikirim ke model

Hanya ringkasan metadata: total ukuran, sisa disk, daftar duplikat, berkas besar, berkas lama, tipe
berkas terbesar, dan 100 berkas terbesar (nama + path + ukuran). **Isi berkas tidak pernah dikirim.**
Nama dan path sengaja disertakan agar sarannya konkret, bukan saran umum.

Duplikat dideteksi lewat hash isi, bukan nama, sehingga berkas yang diganti nama tetap tertangkap.

## Eksekusi

Penghapusan tidak berjalan otomatis. Setelah rencana ditampilkan, kamu harus mengetik `yes`. Tanpa
itu, tidak ada berkas yang disentuh.

## Catatan

- Path berkas ikut terkirim ke penyedia model; jangan jalankan pada folder yang nama berkasnya sensitif.
- Hashing berkas besar memakan waktu. Pindai per subfolder daripada seluruh drive sekaligus.
- Coba dulu di folder percobaan.
