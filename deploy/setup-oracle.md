# Desplegar el bot 24/7 en Oracle Cloud (Always Free)

Objetivo: una VM gratis siempre prendida corriendo `monitor.py --loop` como servicio
`systemd`, chequeando cada 3 min y reiniciándose sola si se cae o si reinicia la máquina.

---

## 1. Crear la cuenta y la VM

1. Entrá a <https://www.oracle.com/cloud/free/> → **Start for free**. Pide tarjeta para
   verificar identidad, pero los recursos **Always Free no se cobran**.
2. En la consola: **Compute → Instances → Create instance**.
   - **Image**: Canonical **Ubuntu 22.04** (o 24.04).
   - **Shape**: elegí una marcada **"Always Free-eligible"**:
     - `VM.Standard.E2.1.Micro` (x86, 1 GB RAM) — siempre disponible, alcanza de sobra, **recomendada**.
     - o `VM.Standard.A1.Flex` (ARM Ampere) si querés más potencia.
   - **SSH keys**: subí tu clave pública (o generá una; guardá la privada).
3. **Create**. Cuando esté "Running", anotá la **Public IP**.

> No hace falta abrir ningún puerto de entrada: el bot solo hace llamadas **salientes**
> (a flylevel.com y a Telegram). Dejá las reglas de red por defecto.

---

## 2. Conectarte por SSH

Desde tu PC (PowerShell o terminal):

```bash
ssh ubuntu@TU_IP_PUBLICA
```

(En Ubuntu de Oracle el usuario por defecto es `ubuntu`.)

---

## 3. Instalar dependencias del sistema

```bash
sudo apt update
sudo apt install -y python3 python3-venv git
```

---

## 4. Subir el código

**Opción A — si ya lo tenés en GitHub:**

```bash
git clone https://github.com/TU_USUARIO/flylevel-bot.git
cd flylevel-bot
```

**Opción B — copiarlo desde tu PC** (corré esto en TU PC, no en la VM):

```bash
scp -r C:\Users\Jchi\flylevel-bot ubuntu@TU_IP_PUBLICA:/home/ubuntu/flylevel-bot
```

La carpeta final debe quedar en `/home/ubuntu/flylevel-bot` (es la ruta que usa el servicio).

---

## 5. Entorno Python + dependencias

```bash
cd /home/ubuntu/flylevel-bot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

---

## 6. Configurar los secrets (.env)

```bash
cp deploy/.env.example .env
nano .env          # completá TELEGRAM_TOKEN y revisá el resto
chmod 600 .env     # solo tu usuario puede leerla
```

Probá que Telegram funcione antes de prender el servicio:

```bash
set -a; . ./.env; set +a
.venv/bin/python monitor.py --test-telegram
```

Te tiene que llegar el mensaje de prueba. ✅

---

## 7. Instalar el servicio systemd

```bash
sudo cp deploy/flylevel-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now flylevel-bot
```

`enable --now` lo arranca y lo deja configurado para iniciar solo en cada boot.

---

## 8. Verificar que corre

```bash
systemctl status flylevel-bot          # debe decir "active (running)"
journalctl -u flylevel-bot -f          # logs en vivo (Ctrl+C para salir)
```

En los logs vas a ver cada pasada: `Listo. Consultas: 32. Alertas nuevas: 0.`
(32 = 4 rutas × 2 tipos × 4 meses.)

---

## Comandos útiles

```bash
sudo systemctl restart flylevel-bot    # reiniciar (p.ej. tras editar config.py o .env)
sudo systemctl stop flylevel-bot       # frenar
journalctl -u flylevel-bot --since "1 hour ago"   # logs recientes
```

- **Cambiar frecuencia/umbral**: editá `.env` (`CHECK_INTERVAL`, `ALERT_THRESHOLD`) y `restart`.
- **Cambiar rutas/meses/tags**: editá `config.py` y `restart`.
- El historial anti-spam vive en `state.json` dentro de la carpeta y **persiste** entre
  reinicios (no se pierde como pasaría en GitHub Actions).
