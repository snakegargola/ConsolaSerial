# Publicar proyecto en GitHub (primer release)

## 1) Inicializar repo local (si aún no existe)

```bash
git init
git add .
git commit -m "feat: initial release of Serial Monitor"
```

## 2) Conectar con tu repositorio remoto

```bash
git branch -M main
git remote add origin https://github.com/<TU_USUARIO>/<TU_REPO>.git
git push -u origin main
```

## 3) Crear tag de versión

```bash
git tag -a v1.0.0 -m "v1.0.0"
git push origin v1.0.0
```

## 4) Crear release en GitHub

En GitHub: **Releases > Draft a new release**

- Tag: `v1.0.0`
- Título: `Serial Monitor v1.0.0`
- Descripción: usa `.github/release-template.md`
- Adjuntar artefactos compilados:
  - Linux: `dist/linux/SerialMonitor`, `dist/linux/config.json`
  - Windows: `dist/windows/SerialMonitor.exe`, `dist/windows/config.json`

## 5) Verificación rápida

- README visible y claro
- LICENSE presente
- Build docs correctos
- Archivos pesados y venv excluidos por `.gitignore`
