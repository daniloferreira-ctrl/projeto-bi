"""
Recorta a PESSOA de um vídeo (tira o fundo, quadro a quadro) para o pódio.

Uso:   python recortar_video.py <arquivo do vídeo> <nome da pessoa>
Ex.:   python recortar_video.py "assets/fotos/videos/meu_video.mp4" rafael_nunes

Gera:  assets/fotos/recorte/<nome>.webm   (vídeo com fundo transparente)
       (a foto parada continua sendo a sua: assets/fotos/recorte/<nome>.png)

Precisa: pip install "rembg[cpu]"   e o ffmpeg instalado (winget install ffmpeg).
Vídeos curtos (3–6 s) ficam melhores: cada quadro é processado pela IA.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image
from rembg import new_session, remove

SAIDA = Path(__file__).parent / "assets" / "fotos" / "recorte"
LARGURA = 480          # largura final do vídeo (leve para o navegador)
FPS = 24


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return
    video, nome = Path(sys.argv[1]), sys.argv[2].lower().replace(" ", "_")
    if not shutil.which("ffmpeg"):
        print("ffmpeg não encontrado. Instale com:  winget install ffmpeg   (e reabra o VS Code)")
        return
    SAIDA.mkdir(parents=True, exist_ok=True)
    sessao = new_session("u2net_human_seg")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "in").mkdir(); (tmp / "out").mkdir()
        subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(video), "-vf", f"fps={FPS},scale={LARGURA}:-2",
                        str(tmp / "in" / "q%04d.png")], check=True)
        quadros = sorted((tmp / "in").glob("*.png"))
        caixa = None
        recortes = []
        for i, q in enumerate(quadros, 1):
            print(f"\rRecortando quadro {i}/{len(quadros)}", end="")
            r = remove(Image.open(q).convert("RGBA"), session=sessao)
            b = r.getbbox()
            if b:
                caixa = b if caixa is None else (min(caixa[0], b[0]), min(caixa[1], b[1]),
                                                 max(caixa[2], b[2]), max(caixa[3], b[3]))
            recortes.append(r)
        print()
        # mesmo enquadramento em todos os quadros (a pessoa não "pula" no vídeo)
        l, t, r_, b_ = caixa
        l, t = l - l % 2, t - t % 2
        r_, b_ = r_ + (r_ - l) % 2, b_ + (b_ - t) % 2
        for i, img in enumerate(recortes):
            img.crop((l, t, r_, b_)).save(tmp / "out" / f"q{i:04d}.png")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-framerate", str(FPS), "-i", str(tmp / "out" / "q%04d.png"),
                        "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "34", "-deadline", "good",
                        "-auto-alt-ref", "0", "-an", str(SAIDA / f"{nome}.webm")], check=True)
    print(f"Pronto: {SAIDA / (nome + '.webm')}")


if __name__ == "__main__":
    main()
