"""
AI TUTOR BAHASA INDONESIA - versi 4 (siswa + dasbor guru)
Data materi, bacaan, bank soal, rubrik, CP/TP/ATP dibaca dari tutor22_v2.py
(simpan kedua file di folder yang sama; file lama tidak perlu diubah).

Aktivitas siswa disimpan ke data_belajar.db (SQLite, dibuat otomatis di folder yang sama).
PIN guru: isi PIN_GURU di .streamlit/secrets.toml atau variabel lingkungan PIN_GURU.
Jika tidak diisi, PIN sementara adalah "guru123" (segera ganti).

Jalankan dengan: python -m streamlit run tutor22_v4.py
"""

import hmac
import html
import json
import os
import random
import re
import sqlite3
from collections import Counter
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="AI Tutor Bahasa Indonesia", page_icon="📚", layout="wide")

# ---------------------------------------------------------
# Muat data dari file lama (hanya bagian data, tanpa tampilan lama)
# ---------------------------------------------------------
_src = Path(__file__).with_name("tutor22_v2.py").read_text(encoding="utf-8")
_a, _b = _src.index("# TEKS BACAAN"), _src.index("# SIDEBAR")
exec(compile(_src[_src.rfind("\n", 0, _a) + 1:_b], "data_v2", "exec"), globals())

# ---------------------------------------------------------
# CSS
# ---------------------------------------------------------
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Baloo+2:wght@600;800&family=Nunito:wght@400;600;700&display=swap');
:root { --ink:#1F2340; --teal:#0E7C86; --sun:#FFC145; --pink:#FF6B8A; }
html, body, [class*="css"] { font-family:'Nunito', Arial, sans-serif; font-size:18px; }
h1, h2, h3, .judul { font-family:'Baloo 2', sans-serif !important; color:var(--ink); }
.stApp { background:linear-gradient(180deg,#F1F9FA 0%,#FFFFFF 45%); }
p, div[data-testid="stMarkdownContainer"] p { line-height:1.7 !important; }
section[data-testid="stSidebar"] { background:var(--ink); }
section[data-testid="stSidebar"] * { color:#F4FAFB; }
.stProgress > div > div > div > div { background-color:var(--sun); }
.stButton > button {
    border-radius:14px; border:2px solid var(--teal); font-weight:700;
    padding:10px 18px; transition:transform .15s, box-shadow .15s;
}
.stButton > button:hover:not(:disabled) {
    transform:translateY(-2px); box-shadow:0 6px 14px rgba(14,124,134,.25); border-color:var(--pink);
}
.hero {
    background:linear-gradient(120deg,var(--teal),var(--ink)); color:#fff;
    padding:30px 34px; border-radius:24px; margin-bottom:22px;
}
.hero .judul { color:#fff; font-size:38px; font-weight:800; line-height:1.15; }
.hero p { color:#DDF3F5; margin:8px 0 0; font-size:19px; }
.stat {
    background:#fff; border-radius:16px; padding:14px 18px; border-left:6px solid var(--sun);
    box-shadow:0 2px 10px rgba(31,35,64,.08); margin-bottom:10px;
}
.stat .angka { font-family:'Baloo 2'; font-size:30px; font-weight:800; color:var(--teal); }
.xpbox { background:rgba(255,255,255,.1); border-radius:14px; padding:12px 14px; margin-bottom:8px; }
.question-box {
    padding:18px 20px; border-radius:14px; background:#fff; border:2px dashed var(--teal);
    margin-bottom:15px; line-height:1.8; white-space:pre-line;
}
.kartu {
    min-height:190px; display:flex; align-items:center; justify-content:center; text-align:center;
    padding:24px; border-radius:24px; font-family:'Baloo 2'; font-size:30px; font-weight:600;
    box-shadow:0 8px 20px rgba(31,35,64,.15); margin-bottom:14px;
}
.kartu.depan { background:var(--teal); color:#fff; }
.kartu.belakang { background:var(--sun); color:var(--ink); font-size:24px; }
.kredit { background:#fff; border-radius:16px; padding:16px 20px; border-left:6px solid var(--pink);
    box-shadow:0 2px 10px rgba(31,35,64,.08); }
.kredit .judul { font-size:22px; font-weight:800; }
.kredit span { display:inline-block; background:#F1F9FA; border-radius:999px;
    padding:4px 14px; margin:4px 6px 0 0; font-weight:700; color:var(--ink); }
mark.k { background:var(--sun); padding:0 5px; border-radius:6px; font-weight:700; }
mark { padding:0 4px; border-radius:6px; }
@media (prefers-reduced-motion: reduce) { .stButton > button { transition:none; } }
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# State, XP, dan lencana
# ---------------------------------------------------------
ss = st.session_state
for _k, _v in {
    "xp": 0, "streak": 0, "best": 0, "selesai": set(), "badges": set(), "misi": set(),
    "kuis": None, "chat": [], "aktif": list(MATERI)[0], "kartu": 0, "flip": False,
    "dikenal": 0, "dk_done": set(), "dk_benar": 0,
    "peran": None, "nama": "", "kelas": "", "cek_log": set(), "dk_log": set(),
}.items():
    ss.setdefault(_k, _v)

LENCANA = {
    "rajin": "📘 Pembaca Rajin (5 materi selesai)",
    "detektif": "🕵️ Detektif Konjungsi (5 jawaban benar)",
    "sempurna": "💯 Kuis Sempurna",
    "api": "🔥 Api Semangat (5 jawaban beruntun)",
    "kolektor": "🃏 Kolektor Kartu (10 kartu dikenal)",
}
MISI = {
    "materi": "Selesaikan 1 materi",
    "kuis": "Selesaikan 1 kuis cepat",
    "detektif": "Jawab 1 soal Detektif Teks dengan benar",
}


def beri_xp(n, pesan=""):
    ss.xp += n
    st.toast(f"+{n} XP {pesan}".strip(), icon="⭐")


def buka_lencana(kode):
    if kode not in ss.badges:
        ss.badges.add(kode)
        st.toast(f"Lencana baru: {LENCANA[kode]}", icon="🏅")


M_BERANDA, M_PETA, M_KUIS, M_KARTU = "🏠 Beranda", "🗺️ Peta Belajar", "⚡ Kuis Cepat", "🃏 Kartu Kilat"
M_DETEKTIF, M_TUTOR, M_RUBRIK = "🕵️ Detektif Teks", "🤖 Tanya Tutor", "📊 Nilai Diriku"
M_CP, M_REFLEKSI, M_INFO = "🎓 CP, TP, dan ATP", "🪞 Refleksi", "ℹ️ Ketentuan"
SEMUA_MENU = [M_BERANDA, M_PETA, M_KUIS, M_KARTU, M_DETEKTIF, M_TUTOR, M_RUBRIK, M_CP, M_REFLEKSI, M_INFO]


KELOMPOK = "Kelompok 3"
ANGGOTA = ["Febri Simamora", "Pintauli Silaban", "Nopita Silaban",
           "Osmer Nadeak", "Grace Tampubolon", "Hanna Sianturi"]


def pindah(m):
    ss.menu = m


def stat(label, nilai):
    return f'<div class="stat"><div class="angka">{nilai}</div>{label}</div>'


# ---------------------------------------------------------
# Penyimpanan data belajar (SQLite)
# Satu tabel "log": setiap aksi siswa menjadi satu baris.
# jenis: masuk | materi | soal | kuis | detektif | rubrik | refleksi
# ---------------------------------------------------------
DB_PATH = Path(__file__).with_name("data_belajar.db")
try:
    from zoneinfo import ZoneInfo
    WIB = ZoneInfo("Asia/Jakarta")
except Exception:  # Windows tanpa paket tzdata
    WIB = None

ASPEK_REFLEKSI = [
    "Teks deskripsi, tujuan, dan cirinya", "Ide pokok dan letaknya", "Informasi tersurat",
    "Informasi tersirat", "Arti kata dari kamus dan konteks", "Sudut pandang dan buku harian",
    "Fungsi konjungsi", "Kosakata serapan", "Kohesi dan koherensi", "Informasi dalam infografik",
    "Menginterpretasikan, membandingkan, mengevaluasi",
]


def sekarang():
    return (datetime.now(WIB) if WIB else datetime.now()).replace(tzinfo=None)


def _koneksi():
    return closing(sqlite3.connect(DB_PATH, timeout=10))


def init_db():
    with _koneksi() as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS log ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, waktu TEXT NOT NULL, nama TEXT NOT NULL, "
            "kelas TEXT NOT NULL, jenis TEXT NOT NULL, materi TEXT, benar INTEGER, "
            "nilai REAL, detail TEXT)"
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_log_siswa ON log(nama, kelas)")
        c.commit()


def catat(jenis, materi=None, benar=None, nilai=None, detail=None):
    """Simpan satu aktivitas siswa. Gagal menyimpan tidak boleh merusak pembelajaran."""
    if ss.peran != "siswa" or not ss.nama:
        return
    try:
        with _koneksi() as c:
            c.execute(
                "INSERT INTO log (waktu, nama, kelas, jenis, materi, benar, nilai, detail) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (sekarang().isoformat(timespec="seconds"), ss.nama, ss.kelas, jenis,
                 materi, benar, nilai, detail),
            )
            c.commit()
    except sqlite3.Error:
        st.toast("Aktivitas ini belum tersimpan untuk guru.", icon="⚠️")


def muat_log():
    with _koneksi() as c:
        return pd.read_sql_query("SELECT * FROM log", c)


def pin_guru():
    try:
        return str(st.secrets["PIN_GURU"])
    except Exception:
        return os.environ.get("PIN_GURU", "guru123")


def keluar():
    for k in list(ss.keys()):
        del ss[k]


init_db()

# ---------------------------------------------------------
# Dasbor guru
# ---------------------------------------------------------
H_RINGKAS, H_SISWA, H_MATERI = "📋 Ringkasan", "👥 Daftar Siswa", "📚 Analisis Materi"
H_SOAL, H_DETAIL, H_REFLEKSI, H_EKSPOR = "❓ Soal Tersulit", "🔍 Detail Siswa", "🪞 Refleksi Kelas", "⬇️ Ekspor Data"
H_GAMBAR = "🖼️ Kelola Gambar"
HALAMAN_GURU = [H_RINGKAS, H_SISWA, H_MATERI, H_SOAL, H_DETAIL, H_REFLEKSI, H_GAMBAR, H_EKSPOR]

# ---------------------------------------------------------
# Gambar pendamping materi
# File disimpan di folder gambar/ dengan nama <nomor materi>_<nama>.png.
# Keterangan (termasuk sumber gambar) disimpan di gambar/keterangan.json.
# ---------------------------------------------------------
GAMBAR_DIR = Path(__file__).with_name("gambar")
GAMBAR_DIR.mkdir(exist_ok=True)
KET_FILE = GAMBAR_DIR / "keterangan.json"
FORMAT_GAMBAR = ["png", "jpg", "jpeg", "webp", "gif"]
MAKS_GAMBAR = 2 * 1024 * 1024


def nomor_materi(nama):
    return nama.split(".", 1)[0].strip()


def daftar_gambar(nama):
    return sorted(p for p in GAMBAR_DIR.glob(f"{nomor_materi(nama)}_*")
                  if p.suffix.lower().lstrip(".") in FORMAT_GAMBAR)


def muat_ket():
    try:
        return json.loads(KET_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def simpan_ket(d):
    KET_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def keterangan(p, ket):
    return ket.get(p.name) or p.stem.split("_", 1)[-1].replace("-", " ").replace("_", " ").capitalize()


def tampil_gambar(nama):
    files = daftar_gambar(nama)
    if not files:
        return
    ket = muat_ket()
    cols = st.columns(min(len(files), 3))
    for i, p in enumerate(files):
        cols[i % len(cols)].image(str(p), caption=keterangan(p, ket), use_container_width=True)


def kelola_gambar():
    st.subheader("Gambar pendamping materi")
    st.caption("Gambar tampil di Peta Belajar pada materi yang dipilih. Pakai foto atau gambar buatan sendiri, "
               "atau yang berlisensi bebas, dan tulis sumbernya di keterangan.")
    nama = st.selectbox("Materi", list(MATERI))
    ket = muat_ket()
    ada = daftar_gambar(nama)
    if not ada:
        st.info("Materi ini belum punya gambar.")
    for p in ada:
        c1, c2 = st.columns([4, 1])
        c1.image(str(p), caption=keterangan(p, ket), width=260)
        if c2.button("🗑️ Hapus", key=f"hapus_{p.name}"):
            p.unlink(missing_ok=True)
            ket.pop(p.name, None)
            simpan_ket(ket)
            st.rerun()
    st.divider()
    with st.form("unggah_gambar", clear_on_submit=True):
        berkas = st.file_uploader("Unggah gambar (maksimal 2 MB per berkas)", type=FORMAT_GAMBAR,
                                  accept_multiple_files=True)
        isi = st.text_input("Keterangan gambar (boleh dengan sumber)",
                            placeholder="Contoh: Pemandangan Danau Toba. Foto: milik sendiri")
        ok = st.form_submit_button("💾 Simpan gambar")
    if ok:
        from PIL import Image
        tersimpan = 0
        for f in berkas:
            if f.size > MAKS_GAMBAR:
                st.warning(f"{f.name} lebih dari 2 MB, perkecil dulu.")
                continue
            try:
                Image.open(f).verify()
            except Exception:
                st.warning(f"{f.name} bukan gambar yang valid.")
                continue
            f.seek(0)
            slug = re.sub(r"[^a-z0-9]+", "-", Path(f.name).stem.lower()).strip("-") or "gambar"
            tujuan, n = GAMBAR_DIR / f"{nomor_materi(nama)}_{slug}{Path(f.name).suffix.lower()}", 2
            while tujuan.exists():
                tujuan = tujuan.with_name(f"{nomor_materi(nama)}_{slug}-{n}{tujuan.suffix}")
                n += 1
            tujuan.write_bytes(f.getbuffer())
            if isi.strip():
                ket[tujuan.name] = isi.strip()
            tersimpan += 1
        if tersimpan:
            simpan_ket(ket)
            st.success(f"{tersimpan} gambar tersimpan.")
            st.rerun()



def persen(seri):
    return None if len(seri) == 0 else round(float(seri.mean()) * 100)


def status_siswa(akurasi, n_soal, hari):
    cat = []
    if n_soal >= 5 and akurasi is not None and akurasi < 60:
        cat.append("Akurasi rendah")
    if hari >= 7:
        cat.append("Lama tidak aktif")
    return ", ".join(cat) or "Lancar"


def buat_rekap(df):
    baris = []
    for (nama, kelas), g in df.groupby(["nama", "kelas"]):
        soal, kuis = g[g["jenis"] == "soal"], g[g["jenis"] == "kuis"]
        akurasi = persen(soal["benar"])
        terakhir = g["waktu"].max()
        hari = (sekarang() - terakhir).days
        baris.append({
            "Nama": nama, "Kelas": kelas,
            "Materi selesai": g[g["jenis"] == "materi"]["materi"].nunique(),
            "Soal dijawab": len(soal), "Akurasi (%)": akurasi,
            "Kuis selesai": len(kuis),
            "Rata-rata kuis": None if kuis.empty else round(kuis["nilai"].mean()),
            "Terakhir aktif": terakhir,
            "Status": status_siswa(akurasi, len(soal), hari),
        })
    return pd.DataFrame(baris)


def baca_refleksi(df):
    hasil = []
    for _, r in df[df["jenis"] == "refleksi"].sort_values("waktu").iterrows():
        try:
            d = json.loads(r["detail"])
        except (TypeError, ValueError):
            continue
        if isinstance(d, dict):
            d.update(nama=r["nama"], kelas=r["kelas"], waktu=r["waktu"])
            hasil.append(d)
    return pd.DataFrame(hasil)


def tampil_dasbor():
    with st.sidebar:
        st.markdown("**👩‍🏫 Dasbor Guru**")
        halaman = st.radio("Halaman", HALAMAN_GURU, key="menu_guru", label_visibility="collapsed")
        st.button("🚪 Keluar", on_click=keluar, use_container_width=True)
        st.caption(f"Dibuat oleh {KELOMPOK}")

    st.markdown(
        '<div class="hero"><div class="judul">Dasbor Guru</div>'
        "<p>Lihat siapa yang butuh bantuan, materi mana yang belum dipahami, dan apa kata siswa tentang belajarnya.</p></div>",
        unsafe_allow_html=True,
    )
    if halaman == H_GAMBAR:
        kelola_gambar()
        return
    df = muat_log()
    if df.empty:
        st.info("Belum ada data. Data muncul setelah siswa masuk dan mulai belajar.")
        return
    df["waktu"] = pd.to_datetime(df["waktu"])

    kelas_pilih = st.selectbox("Kelas", ["Semua kelas"] + sorted(df["kelas"].unique()))
    if kelas_pilih != "Semua kelas":
        df = df[df["kelas"] == kelas_pilih]
    rekap = buat_rekap(df)
    soal = df[df["jenis"] == "soal"]

    if halaman == H_RINGKAS:
        kuis = df[df["jenis"] == "kuis"]
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(stat("Siswa terdata", len(rekap)), unsafe_allow_html=True)
        c2.markdown(stat("Soal dijawab", len(soal)), unsafe_allow_html=True)
        c3.markdown(stat("Akurasi rata-rata", "-" if soal.empty else f"{persen(soal['benar'])}%"),
                    unsafe_allow_html=True)
        c4.markdown(stat("Rata-rata nilai kuis", "-" if kuis.empty else round(kuis["nilai"].mean())),
                    unsafe_allow_html=True)

        st.subheader("Siswa yang perlu perhatian")
        butuh = rekap[rekap["Status"] != "Lancar"]
        if butuh.empty:
            st.success("Semua siswa yang terdata berjalan lancar.")
        else:
            st.dataframe(butuh[["Nama", "Kelas", "Akurasi (%)", "Soal dijawab", "Terakhir aktif", "Status"]],
                         use_container_width=True, hide_index=True)
            st.caption("Akurasi rendah: di bawah 60% setelah minimal 5 soal. "
                       "Lama tidak aktif: 7 hari atau lebih tanpa aktivitas.")

        st.subheader("Aktivitas harian")
        harian = df[df["jenis"] != "masuk"].set_index("waktu").resample("D").size()
        if harian.empty:
            st.caption("Belum ada aktivitas belajar.")
        else:
            st.bar_chart(harian.tail(30))

    elif halaman == H_SISWA:
        st.subheader("Rekap per siswa")
        st.dataframe(
            rekap.sort_values(["Kelas", "Nama"]), use_container_width=True, hide_index=True,
            column_config={
                "Materi selesai": st.column_config.ProgressColumn(
                    "Materi selesai", min_value=0, max_value=len(MATERI), format="%d"),
                "Akurasi (%)": st.column_config.ProgressColumn(
                    "Akurasi (%)", min_value=0, max_value=100, format="%d"),
                "Terakhir aktif": st.column_config.DatetimeColumn("Terakhir aktif", format="DD/MM/YYYY HH:mm"),
            },
        )

    elif halaman == H_MATERI:
        st.subheader("Penguasaan per materi")
        if soal.empty:
            st.info("Belum ada jawaban soal.")
        else:
            per = soal.groupby("materi")["benar"].agg(["mean", "count"]).reset_index()
            per.columns = ["Materi", "Akurasi (%)", "Jumlah jawaban"]
            per["Akurasi (%)"] = (per["Akurasi (%)"] * 100).round()
            per = per.sort_values("Akurasi (%)")
            lemah = per[per["Jumlah jawaban"] >= 5].head(3)
            if not lemah.empty:
                st.warning("Layak diulang di kelas: " + "; ".join(lemah["Materi"]))
            st.dataframe(per, use_container_width=True, hide_index=True, column_config={
                "Akurasi (%)": st.column_config.ProgressColumn(
                    "Akurasi (%)", min_value=0, max_value=100, format="%d")})
            st.caption("Urutan dari akurasi terendah. Materi dengan kurang dari 5 jawaban belum cukup untuk disimpulkan.")

        st.subheader("Penyelesaian materi")
        selesai = df[df["jenis"] == "materi"].groupby("materi")["nama"].nunique()
        tabel = pd.DataFrame({"Materi": list(MATERI),
                              "Siswa selesai": [int(selesai.get(m, 0)) for m in MATERI]})
        st.dataframe(tabel, use_container_width=True, hide_index=True)

    elif halaman == H_SOAL:
        st.subheader("Soal yang paling sering salah")
        s = soal.dropna(subset=["detail"])
        if s.empty:
            st.info("Belum ada jawaban soal.")
        else:
            g = s.groupby("detail").agg(Materi=("materi", "first"), rata=("benar", "mean"),
                                        Jawaban=("benar", "count")).reset_index()
            g = g[g["Jawaban"] >= 3]
            g["Salah (%)"] = ((1 - g["rata"]) * 100).round()
            g = g.sort_values(["Salah (%)", "Jawaban"], ascending=False).head(10)
            g = g.rename(columns={"detail": "Pertanyaan"})[["Pertanyaan", "Materi", "Salah (%)", "Jawaban"]]
            if g.empty:
                st.info("Soal ditampilkan setelah dijawab minimal 3 kali.")
            else:
                st.dataframe(g, use_container_width=True, hide_index=True)

        st.subheader("Konjungsi di Detektif Teks")
        d = df[df["jenis"] == "detektif"]
        if d.empty:
            st.caption("Belum ada jawaban Detektif Teks.")
        else:
            k = d.groupby("detail")["benar"].agg(["mean", "count"]).reset_index()
            k.columns = ["Konjungsi", "Benar (%)", "Jawaban"]
            k["Benar (%)"] = (k["Benar (%)"] * 100).round()
            st.dataframe(k.sort_values("Benar (%)"), use_container_width=True, hide_index=True)

    elif halaman == H_DETAIL:
        pilihan = {f"{r.Nama} ({r.Kelas})": (r.Nama, r.Kelas) for r in rekap.itertuples()}
        label = st.selectbox("Pilih siswa", sorted(pilihan))
        nama, kelas = pilihan[label]
        g = df[(df["nama"] == nama) & (df["kelas"] == kelas)]
        r = rekap[(rekap["Nama"] == nama) & (rekap["Kelas"] == kelas)].iloc[0]

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Materi selesai", f"{r['Materi selesai']}/{len(MATERI)}")
        m2.metric("Soal dijawab", r["Soal dijawab"])
        m3.metric("Akurasi", "-" if pd.isna(r["Akurasi (%)"]) else f"{int(r['Akurasi (%)'])}%")
        m4.metric("Rata-rata kuis", "-" if pd.isna(r["Rata-rata kuis"]) else int(r["Rata-rata kuis"]))
        st.write(f"Status: **{r['Status']}**")

        selesai = set(g[g["jenis"] == "materi"]["materi"])
        with st.expander("Materi yang belum selesai"):
            sisa_materi = [m for m in MATERI if m not in selesai]
            st.write("\n".join(f"- {m}" for m in sisa_materi) if sisa_materi else "Semua materi sudah selesai.")

        gs = g[g["jenis"] == "soal"]
        if not gs.empty:
            st.subheader("Akurasi per materi")
            p = gs.groupby("materi")["benar"].agg(["mean", "count"]).reset_index()
            p.columns = ["Materi", "Akurasi (%)", "Jawaban"]
            p["Akurasi (%)"] = (p["Akurasi (%)"] * 100).round()
            st.dataframe(p.sort_values("Akurasi (%)"), use_container_width=True, hide_index=True)

        gk = g[g["jenis"] == "kuis"]
        if len(gk) >= 2:
            st.subheader("Perkembangan nilai kuis")
            st.line_chart(gk.set_index("waktu")["nilai"])

        ref = baca_refleksi(g)
        if not ref.empty:
            t = ref.iloc[-1]
            st.subheader("Refleksi terbaru")
            st.write(f"Perasaan: {t.get('mood', '')}")
            st.write(f"Paling sulit: {t.get('sulit') or '-'}")
            st.write(f"Rencana perbaikan: {t.get('perbaikan') or '-'}")
            st.write(f"Meminta bantuan kepada: {t.get('bantuan') or '-'}")

        with st.expander("Riwayat aktivitas"):
            st.dataframe(g.sort_values("waktu", ascending=False)[["waktu", "jenis", "materi", "benar", "nilai"]],
                         use_container_width=True, hide_index=True)

    elif halaman == H_REFLEKSI:
        ref = baca_refleksi(df)
        if ref.empty:
            st.info("Belum ada refleksi yang dikirim siswa.")
        else:
            terbaru = ref.drop_duplicates(["nama", "kelas"], keep="last")
            st.caption(f"Berdasarkan refleksi terbaru dari {len(terbaru)} siswa.")
            belum = Counter()
            for p in terbaru["paham"]:
                p = p if isinstance(p, list) else []
                belum.update(a for a in ASPEK_REFLEKSI if a not in p)
            st.subheader("Bagian yang masih perlu diulang (jumlah siswa)")
            st.bar_chart(pd.Series({a: belum.get(a, 0) for a in ASPEK_REFLEKSI}))

            st.subheader("Perasaan siswa")
            st.bar_chart(terbaru["mood"].value_counts())

            st.subheader("Suara siswa")
            teks = terbaru.rename(columns={"nama": "Nama", "kelas": "Kelas", "sulit": "Paling sulit",
                                           "perbaikan": "Rencana perbaikan", "bantuan": "Minta bantuan kepada"})
            st.dataframe(teks[["Nama", "Kelas", "Paling sulit", "Rencana perbaikan", "Minta bantuan kepada"]],
                         use_container_width=True, hide_index=True)

    elif halaman == H_EKSPOR:
        st.subheader("Unduh data")
        st.write("Berkas CSV bisa dibuka langsung di Excel atau Google Sheets.")
        st.download_button("⬇️ Rekap per siswa (CSV)", rekap.to_csv(index=False).encode("utf-8-sig"),
                           file_name="rekap_siswa.csv", mime="text/csv")
        st.download_button("⬇️ Seluruh log aktivitas (CSV)", df.to_csv(index=False).encode("utf-8-sig"),
                           file_name="log_aktivitas.csv", mime="text/csv")
        st.caption(f"Data asli tersimpan di {DB_PATH.name}. Cadangkan berkas itu secara berkala.")


# ---------------------------------------------------------
# Gerbang masuk: siswa atau guru
# ---------------------------------------------------------
if ss.peran is None:
    st.markdown(
        '<div class="hero"><div class="judul">AI Tutor Bahasa Indonesia</div>'
        "<p>Masuk dulu, supaya kemajuan belajarmu tercatat.</p></div>",
        unsafe_allow_html=True,
    )
    tab_s, tab_g = st.tabs(["🎒 Aku siswa", "👩‍🏫 Aku guru"])
    with tab_s:
        with st.form("masuk_siswa"):
            in_nama = st.text_input("Nama lengkap")
            in_kelas = st.text_input("Kelas", placeholder="Contoh: IX-A")
            ok = st.form_submit_button("🚀 Mulai belajar")
        if ok:
            n, kl = " ".join(in_nama.split()).title(), in_kelas.strip().upper()
            if len(n) < 3 or not kl:
                st.error("Isi nama lengkap dan kelas dulu ya.")
            else:
                ss.peran, ss.nama, ss.kelas = "siswa", n, kl
                catat("masuk")
                st.rerun()
        st.caption("Tulis nama dengan ejaan yang sama setiap masuk, agar data belajarmu menyatu.")
    with tab_g:
        with st.form("masuk_guru"):
            in_pin = st.text_input("PIN guru", type="password")
            ok_g = st.form_submit_button("Masuk dasbor")
        if ok_g:
            if hmac.compare_digest(in_pin.encode(), pin_guru().encode()):
                ss.peran = "guru"
                st.rerun()
            else:
                st.error("PIN salah.")
        if "PIN_GURU" not in os.environ and not (Path(__file__).parent / ".streamlit" / "secrets.toml").exists():
            st.warning("PIN masih bawaan (guru123). Atur PIN_GURU sebelum dipakai di kelas.")
    st.stop()

if ss.peran == "guru":
    tampil_dasbor()
    st.divider()
    st.caption(f"AI Tutor Bahasa Indonesia | Dasbor Guru | Dibuat oleh {KELOMPOK}")
    st.stop()


# ---------------------------------------------------------
# Sidebar
# ---------------------------------------------------------
level, sisa = ss.xp // 100 + 1, ss.xp % 100
with st.sidebar:
    st.markdown(
        f'<div class="xpbox"><b>⭐ Level {level}</b> &nbsp; {ss.xp} XP<br>🔥 Beruntun: {ss.streak}</div>',
        unsafe_allow_html=True,
    )
    st.progress(sisa / 100)
    st.caption(f"{100 - sisa} XP lagi menuju level {level + 1}")
    menu = st.radio("Menu", SEMUA_MENU, key="menu", label_visibility="collapsed")
    st.caption(f"👤 {ss.nama} | Kelas {ss.kelas}")
    st.button("🚪 Keluar", on_click=keluar, use_container_width=True)
    st.caption(f"Dibuat oleh {KELOMPOK}")
    if ss.badges:
        st.markdown("**Lencanamu**")
        for b in ss.badges:
            st.write(LENCANA[b])

# ---------------------------------------------------------
# BERANDA
# ---------------------------------------------------------
if menu == M_BERANDA:
    st.markdown(
        '<div class="hero"><div class="judul">Ayo jadi detektif teks deskripsi!</div>'
        "<p>Baca, tebak, jawab, dan kumpulkan XP. Setiap langkah kecil menambah levelmu.</p></div>",
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(stat("Materi selesai", f"{len(ss.selesai)}/{len(MATERI)}"), unsafe_allow_html=True)
    c2.markdown(stat("Level", level), unsafe_allow_html=True)
    c3.markdown(stat("Rekor beruntun", ss.best), unsafe_allow_html=True)
    c4.markdown(stat("Lencana", f"{len(ss.badges)}/{len(LENCANA)}"), unsafe_allow_html=True)

    st.subheader("🎯 Misi hari ini")
    st.progress(len(ss.misi) / len(MISI))
    for kode, teks in MISI.items():
        st.write(("✅ " if kode in ss.misi else "⬜ ") + teks)

    st.subheader("Mau mulai dari mana?")
    b1, b2, b3 = st.columns(3)
    b1.button("🗺️ Belajar materi", on_click=pindah, args=(M_PETA,), use_container_width=True)
    b2.button("⚡ Tantang diriku", on_click=pindah, args=(M_KUIS,), use_container_width=True)
    b3.button("🕵️ Selidiki teks", on_click=pindah, args=(M_DETEKTIF,), use_container_width=True)

    st.subheader("👩‍🎓 Tim Pembuat")
    st.markdown(
        f'<div class="kredit"><div class="judul">{KELOMPOK}</div>'
        + "".join(f"<span>{n}</span>" for n in ANGGOTA)
        + "</div>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------
# PETA BELAJAR
# ---------------------------------------------------------
elif menu == M_PETA:
    st.header("🗺️ Peta Belajar")
    st.progress(len(ss.selesai) / len(MATERI), text=f"{len(ss.selesai)} dari {len(MATERI)} materi selesai")

    cols = st.columns(3)
    for i, nama in enumerate(MATERI):
        ikon = "✅" if nama in ss.selesai else "📖"
        cols[i % 3].button(
            f"{ikon} {nama}", key=f"mt{i}", use_container_width=True,
            on_click=lambda n=nama: ss.update(aktif=n),
        )
    st.divider()

    nama = ss.aktif
    tampilkan_materi(nama)
    tampil_gambar(nama)

    judul = nama.split(". ", 1)[1]
    cek = [s for s in BANK_SOAL if s["materi"] == judul]
    if cek:
        with st.expander("🧠 Cek cepat: sudah paham?"):
            s = cek[0]
            pil = st.radio(s["pertanyaan"], s["opsi"], index=None, key=f"cek_{nama}")
            if pil:
                if f"cek_{nama}" not in ss.cek_log:
                    ss.cek_log.add(f"cek_{nama}")
                    catat("soal", materi=judul, benar=int(pil == s["jawaban"]), detail=s["pertanyaan"])
                if pil == s["jawaban"]:
                    st.success("Tepat! " + s["pembahasan"])
                else:
                    st.error("Belum tepat. " + s["pembahasan"])

    def selesai_materi(n):
        if n not in ss.selesai:
            ss.selesai.add(n)
            catat("materi", materi=n)
            ss.misi.add("materi")
            beri_xp(10, "materi selesai")
            if len(ss.selesai) >= 5:
                buka_lencana("rajin")

    if nama in ss.selesai:
        st.success("Materi ini sudah selesai ✅")
    else:
        st.button("✔️ Tandai selesai (+10 XP)", on_click=selesai_materi, args=(nama,))

# ---------------------------------------------------------
# KUIS CEPAT
# ---------------------------------------------------------
elif menu == M_KUIS:
    st.header("⚡ Kuis Cepat")

    def mulai_kuis(n):
        soal = random.sample(BANK_SOAL, n)
        ss.kuis = {"soal": soal, "opsi": [random.sample(s["opsi"], len(s["opsi"])) for s in soal],
                   "i": 0, "skor": 0, "jawab": None, "beres": False}
        ss.streak = 0

    def jawab(opt):
        k = ss.kuis
        if k["jawab"] is not None:
            return
        k["jawab"] = opt
        sk = k["soal"][k["i"]]
        catat("soal", materi=sk["materi"], benar=int(opt == sk["jawaban"]), detail=sk["pertanyaan"])
        if opt == k["soal"][k["i"]]["jawaban"]:
            k["skor"] += 1
            ss.streak += 1
            ss.best = max(ss.best, ss.streak)
            beri_xp(5 + (2 if ss.streak >= 3 else 0), "jawaban benar")
            if ss.streak >= 5:
                buka_lencana("api")
        else:
            ss.streak = 0

    def lanjut():
        ss.kuis["i"] += 1
        ss.kuis["jawab"] = None

    def ulang():
        ss.kuis = None

    k = ss.kuis
    if k is None:
        n = st.slider("Berapa soal?", 5, len(BANK_SOAL), 10)
        st.write("Klik jawabanmu, hasilnya langsung terlihat. Jawab benar berturut-turut untuk bonus XP!")
        st.button("🚀 Mulai kuis", on_click=mulai_kuis, args=(n,))
    elif k["i"] >= len(k["soal"]):
        total = len(k["soal"])
        nilai = round(k["skor"] / total * 100)
        if not k["beres"]:
            k["beres"] = True
            catat("kuis", nilai=nilai, detail=f"{k['skor']}/{total}")
            ss.misi.add("kuis")
            beri_xp(10, "kuis selesai")
            if nilai == 100:
                beri_xp(20, "bonus nilai sempurna")
                buka_lencana("sempurna")
            if nilai >= 80:
                st.balloons()
        st.subheader(f"Nilai kamu: {nilai}")
        st.info(f"Predikat: {hitung_predikat(nilai)}. Benar {k['skor']} dari {total} soal.")
        st.button("🔄 Main lagi", on_click=ulang)
    else:
        i, s = k["i"], k["soal"][k["i"]]
        st.progress(i / len(k["soal"]), text=f"Soal {i + 1} dari {len(k['soal'])}")
        st.caption(f"Materi: {s['materi']}   |   🔥 Beruntun: {ss.streak}")
        st.markdown(f'<div class="question-box">{html.escape(s["pertanyaan"])}</div>', unsafe_allow_html=True)
        kolom = st.columns(2)
        for j, opt in enumerate(k["opsi"][i]):
            label = opt
            if k["jawab"] is not None:
                label = ("✅ " if opt == s["jawaban"] else "❌ " if opt == k["jawab"] else "") + opt
            kolom[j % 2].button(label, key=f"q{i}_{j}", on_click=jawab, args=(opt,),
                                disabled=k["jawab"] is not None, use_container_width=True)
        if k["jawab"] is not None:
            if k["jawab"] == s["jawaban"]:
                st.success("Benar! " + s["pembahasan"])
            else:
                st.error(f"Belum tepat. Jawaban yang benar: {s['jawaban']}. {s['pembahasan']}")
            st.button("Lanjut ➜" if i + 1 < len(k["soal"]) else "Lihat hasil 🏁", on_click=lanjut)

# ---------------------------------------------------------
# KARTU KILAT (dari glosarium)
# ---------------------------------------------------------
elif menu == M_KARTU:
    st.header("🃏 Kartu Kilat")
    if "deck" not in ss:
        baris = [b for b in MATERI["22. Glosarium"]["isi"].splitlines() if b.startswith("|")][2:]
        ss.deck = random.sample([tuple(x.strip() for x in b.strip("|").split("|")) for b in baris], len(baris))

    def balik():
        ss.flip = not ss.flip

    def berikut(tahu):
        if tahu:
            ss.dikenal += 1
            beri_xp(2, "kartu dikenal")
            if ss.dikenal >= 10:
                buka_lencana("kolektor")
        ss.kartu = (ss.kartu + 1) % len(ss.deck)
        ss.flip = False

    istilah, arti = ss.deck[ss.kartu]
    st.caption(f"Kartu {ss.kartu + 1} dari {len(ss.deck)}   |   Dikenal: {ss.dikenal}")
    st.markdown(
        f'<div class="kartu {"belakang" if ss.flip else "depan"}">{html.escape(arti if ss.flip else istilah)}</div>',
        unsafe_allow_html=True,
    )
    st.write("Coba ingat artinya dulu, lalu balik kartunya.")
    c1, c2, c3 = st.columns(3)
    c1.button("🔄 Balik kartu", on_click=balik, use_container_width=True)
    c2.button("😎 Aku sudah tahu", on_click=berikut, args=(True,), use_container_width=True)
    c3.button("🤔 Ulangi nanti", on_click=berikut, args=(False,), use_container_width=True)

# ---------------------------------------------------------
# DETEKTIF TEKS
# ---------------------------------------------------------
elif menu == M_DETEKTIF:
    st.header("🕵️ Detektif Teks")
    KONJ = {"oleh karena itu": "Akibat", "sehingga": "Akibat", "karena": "Sebab", "sebab": "Sebab",
            "tetapi": "Pertentangan", "namun": "Pertentangan", "sedangkan": "Pertentangan",
            "serta": "Penambahan", "ketika": "Waktu", "setelah": "Waktu", "sejak": "Waktu",
            "agar": "Tujuan", "jika": "Syarat", "atau": "Pilihan"}
    POLA = re.compile(r"\b(" + "|".join(sorted(KONJ, key=len, reverse=True)) + r")\b", re.I)
    INDRA = {
        "Penglihatan": ("#FFE08A", ["terang", "berwarna", "rapi", "emas", "segar", "bersih", "uap", "hitam", "asap", "cahaya"]),
        "Pendengaran": ("#B8E6F0", ["gemeretak", "bunyi", "suara", "terdengar", "ribut", "sunyi", "riuh"]),
        "Penciuman": ("#FFC9D6", ["aroma", "harum", "wangi"]),
        "Perabaan": ("#CDEBC5", ["hangat", "kasar", "lembut"]),
        "Pengecapan": ("#E4D4F4", ["manis", "gurih", "asin", "pedas"]),
    }

    pilih = st.selectbox("Pilih kasus (bacaan):", list(TEKS_LATIHAN))
    teks = TEKS_LATIHAN[pilih]
    mode = st.radio("Senter yang dipakai:", ["Tanpa senter", "Konjungsi", "Pancaindra"], horizontal=True)

    badan = html.escape(teks)
    if mode == "Konjungsi":
        badan = POLA.sub(lambda m: f'<mark class="k">{m.group(0)}</mark>', badan)
    elif mode == "Pancaindra":
        for _, (warna, kata) in INDRA.items():
            badan = re.sub(r"\b(\w*(?:" + "|".join(kata) + r")\w*)\b",
                           lambda m, w=warna: f'<mark style="background:{w}">{m.group(0)}</mark>',
                           badan, flags=re.I)
        st.caption("Warna: " + ", ".join(INDRA))
    st.markdown(f'<div class="question-box">{badan}</div>', unsafe_allow_html=True)

    st.subheader("Misi: tentukan hubungan konjungsi")
    kalimat = re.split(r"(?<=[.!?])\s+", teks)
    temuan = [(s, POLA.search(s).group(0).lower()) for s in kalimat if POLA.search(s)]
    if not temuan:
        st.info("Teks ini tidak memuat konjungsi yang bisa dilatih. Coba kasus lain!")
    hubungan = sorted(set(KONJ.values()))
    for n, (s, kj) in enumerate(temuan):
        kunci = f"dk_{pilih}_{n}"
        st.markdown(f"**{n + 1}.** {s}")
        pil = st.selectbox(f"Konjungsi '{kj}' menunjukkan hubungan ...", hubungan, index=None,
                           placeholder="Pilih hubungan", key=kunci)
        if pil:
            if kunci not in ss.dk_log:
                ss.dk_log.add(kunci)
                catat("detektif", materi=pilih, benar=int(pil == KONJ[kj]), detail=kj)
            if pil == KONJ[kj]:
                st.success("Tepat!")
                if kunci not in ss.dk_done:
                    ss.dk_done.add(kunci)
                    ss.dk_benar += 1
                    ss.misi.add("detektif")
                    beri_xp(3, "detektif")
                    if ss.dk_benar >= 5:
                        buka_lencana("detektif")
            else:
                st.warning("Belum tepat. Tanyakan: apa hubungan bagian sebelum dan sesudah kata itu?")

# ---------------------------------------------------------
# TANYA TUTOR
# ---------------------------------------------------------
elif menu == M_TUTOR:
    st.header("🤖 Tanya Tutor")
    st.write("Tanyakan konsep yang belum kamu pahami, atau klik salah satu contoh.")
    contoh = ["Apa itu teks deskripsi?", "Bedanya tersurat dan tersirat?", "Apa itu konjungsi?", "Apa itu kohesi?"]
    klik = None
    for kol, t in zip(st.columns(len(contoh)), contoh):
        if kol.button(t, key="contoh_" + t, use_container_width=True):
            klik = t
    for peran, isi in ss.chat:
        with st.chat_message(peran):
            st.markdown(isi)
    q = st.chat_input("Tulis pertanyaanmu di sini...") or klik
    if q:
        jawaban = tutor_response(q)
        ss.chat += [("user", q), ("assistant", jawaban)]
        with st.chat_message("user"):
            st.markdown(q)
        with st.chat_message("assistant"):
            st.markdown(jawaban)

# ---------------------------------------------------------
# NILAI DIRIKU (rubrik interaktif)
# ---------------------------------------------------------
elif menu == M_RUBRIK:
    st.header("📊 Nilai Diriku")
    st.write("Pilih skor yang paling cocok untuk tiap aspek. Deskripsinya muncul di bawah pilihanmu.")
    total = 0
    for a in RUBRIK:
        skor = st.radio(a["aspek"], [1, 2, 3, 4], index=1, horizontal=True, key="rb_" + a["aspek"])
        st.caption(a[str(skor)])
        total += skor
    maks = len(RUBRIK) * 4
    nilai = round(total / maks * 100, 2)
    st.divider()
    st.metric("Nilai", nilai)
    st.progress(nilai / 100)
    st.write(f"Predikat: **{hitung_predikat(nilai)}** (skor {total} dari {maks})")
    if st.button("📨 Kirim penilaian diriku ke guru"):
        catat("rubrik", nilai=nilai, detail=json.dumps(
            {a["aspek"]: ss.get("rb_" + a["aspek"]) for a in RUBRIK}, ensure_ascii=False))
        beri_xp(3, "penilaian diri")
        st.success("Penilaian dirimu sudah terkirim.")

# ---------------------------------------------------------
# CP, TP, ATP
# ---------------------------------------------------------
elif menu == M_CP:
    st.header("🎓 CP, TP, dan ATP")
    tab_cp, tab_tp, tab_atp = st.tabs(["CP", "TP", "ATP"])
    with tab_cp:
        st.subheader("Capaian Pembelajaran Fase F")
        for item in CP_FASE_F:
            st.markdown(f"- {item}")
        st.info("CP adalah kemampuan besar yang harus dicapai peserta didik pada Fase F.")
    with tab_tp:
        st.subheader("Tujuan Pembelajaran")
        st.table([{"Pertemuan": p, "Kode": kd, "Tujuan Pembelajaran": isi} for p, kd, isi in TUJUAN_PEMBELAJARAN])
    with tab_atp:
        st.subheader("Alur Tujuan Pembelajaran")
        st.markdown(f"**Alur materi:** {ALUR_MATERI}")
        st.caption("Dibaca dari kiri ke kanan ➜")
        for kol, (kd, jd) in zip(st.columns(len(ALUR_TP)), ALUR_TP):
            kol.markdown(f'<div class="stat"><b>{kd}</b><br>{jd}</div>', unsafe_allow_html=True)

# ---------------------------------------------------------
# REFLEKSI
# ---------------------------------------------------------
elif menu == M_REFLEKSI:
    st.header("🪞 Refleksi Pembelajaran")
    aspek = ASPEK_REFLEKSI
    paham = st.multiselect("Bagian yang sudah aku kuasai:", aspek)
    belum = [a for a in aspek if a not in paham]
    if belum:
        st.info("Bagian yang masih perlu kuulang: " + "; ".join(belum))
    elif aspek:
        st.success("Semua bagian sudah kamu kuasai. Hebat!")
    mood = st.radio("Perasaanku hari ini:", ["😫", "😕", "🙂", "😄", "🤩"], index=2, horizontal=True)
    sulit = st.text_area("Bagian yang paling sulit bagiku:")
    perbaikan = st.text_area("Yang akan kulakukan untuk memperbaiki hasil belajar:")
    bantuan = st.text_area("Aku akan meminta bantuan kepada:")
    if st.button("💾 Simpan refleksi"):
        ss.refleksi = {"paham": paham, "mood": mood, "sulit": sulit, "perbaikan": perbaikan, "bantuan": bantuan}
        catat("refleksi", detail=json.dumps(ss.refleksi, ensure_ascii=False))
        beri_xp(5, "refleksi")
        st.success("Refleksi tersimpan. Waktu: " + datetime.now().strftime("%d-%m-%Y %H:%M"))

# ---------------------------------------------------------
# KETENTUAN
# ---------------------------------------------------------
elif menu == M_INFO:
    st.header("ℹ️ Ketentuan AI Tutor")
    st.write(
        'Materi dikembangkan dari Bab I "Demi Keluarga" (Bahasa Indonesia SMP/MTs Kelas IX) '
        f"dan terdiri atas {len(MATERI)} materi."
    )
    st.markdown(
        "- Tutor menjelaskan dengan bahasa mudah dan menjawab berdasarkan materi yang tersedia.\n"
        "- Jawaban siswa harus sesuai isi teks dan punya bukti atau alasan.\n"
        "- Latihan dinilai dari hasil dan dari pembahasan kesalahan.\n"
        "- Skor XP dan lencana hanya penyemangat. Pemahaman tetap yang utama."
    )
    st.info("AI Tutor adalah pendamping. Siswa tetap yang membaca, menalar, menjawab, dan merefleksikan belajarnya.")
    with st.expander("Daftar materi"):
        for nama in MATERI:
            st.write("•", nama)

st.divider()
st.caption(f"AI Tutor Bahasa Indonesia | Pembelajaran Teks Deskripsi | SMP/MTs Kelas IX | Dibuat oleh {KELOMPOK}: " + ", ".join(ANGGOTA))