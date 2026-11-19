import sys
from pathlib import Path

from PIL import Image
from rembg import new_session, remove

PASTA = Path(__file__).parent / "assets" / "fotos"
SAIDA = PASTA / "recorte"
EXTENSOES = (".png", ".jpg", ".jpeg", ".webp")


def recortar(arquivo, sessao):
    destino = SAIDA / f"{arquivo.stem}.png"
    if destino.exists():
        print(f"  pulado (já existe): {destino.name}")
        return
    foto = Image.open(arquivo).convert("RGBA")
    pessoa = remove(foto, session=sessao)
    caixa = pessoa.getbbox()
    if caixa:
        pessoa = pessoa.crop(caixa)
    pessoa.thumbnail((900, 1400))
    pessoa.save(destino, optimize=True)
    print(f"  ok: {destino.name}")


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    if len(sys.argv) > 1:
        fotos = [PASTA / n for n in sys.argv[1:]]
    else:
        fotos = sorted(f for f in PASTA.iterdir() if f.is_file() and f.suffix.lower() in EXTENSOES)
    if not fotos:
        print("Nenhuma foto encontrada em", PASTA)
        return
    print("Carregando o modelo (na primeira vez ele é baixado)...")
    sessao = new_session("u2net_human_seg")
    for f in fotos:
        print("Recortando", f.name)
        recortar(f, sessao)
    print("Pronto! Reinicie o painel para ver as fotos novas.")


if __name__ == "__main__":
    main()