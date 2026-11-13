# Por qué perdemos los jueves + revisión de 18 repos (2026-11-13)

## 1. Jueves: los números
Fuente: tus últimas **1,015 apuestas liquidadas en Stake** (11 ene a 12 nov 2026), bajadas desde stake.com/es/my-bets/sports/settled y guardadas en `data/stake_history/bets.csv` (`scripts/stake_history.py`). El día es el de la última pata.

| Día | Apuestas | Neto | ROI | Acierto | % SGM |
|---|---|---|---|---|---|
| Lun | 125 | +$377 | **+25%** | 42% | 17% |
| Mar | 154 | -$147 | -9% | 30% | 15% |
| Mié | 171 | +$118 | +6% | 33% | 12% |
| **Jue** | **127** | **-$305** | **-20%** | 29% | **22%** |
| Vie | 109 | -$59 | -6% | 23% | 12% |
| Sáb | 185 | -$371 | **-23%** | 25% | 11% |
| Dom | 144 | +$548 | **+42%** | 30% | 19% |

**¿Es mala suerte o algo real?** Barajando 20,000 veces las mismas apuestas al azar, un -20% sale 9% de las veces (p = 0.09). Intervalo 95% del ROI de jueves: -45% a +8%. Es una señal, no una prueba.

**Qué lo explica (en orden):**
1. **El NFL de los jueves (TNF): -57%** en 22 apuestas, 14% de acierto. El NFL el resto de días gana +41%. Es el mismo deporte; lo que cambia es el formato.
2. **Un solo partido = todo junto.** El jueves 32% de tus patas son props de jugador (resto de días 17%) y 22% de tus tickets son SGM (-30.5% el jueves). Con un solo juego en la pizarra, todos los tickets dependen del mismo guion y el margen del SGM se acumula.
3. **Apuestas más grandes después de ganar.** Lo que apuestas el jueves sube con lo que ganaste de lunes a miércoles (correlación +0.50): $97 de media tras semana ganadora contra $28 tras semana perdedora. Es el efecto "dinero de la casa".
4. **Sencillas grandes a cuota 1.6-1.9.** Las 5 peores pérdidas del jueves son sencillas de $30 a $98 en la banda 1.50-1.90 (tu "trampa de la moneda al aire"). Sin esas 5, el jueves queda en -4%.
5. **La mezcla (tipo, patas, cuota) solo explica ~7 de los ~25 puntos.** Con lo que apuestas los jueves se esperaba -2%; el resto es TNF + tamaño + varianza.

**El mercado de los jueves (NFL 2023-26, 68 juegos):** total real 47.7 contra línea 45.1, over 57%, local gana 63% (resto 53%), favorito cubre 46%. Muestra chica (error ±1.7 pts); no es una ventaja validada, pero va contra los unders de props.

**Qué cambió en el sistema:**
- `scripts/slip_linter.py` → `day_guard`: avisa cuando el día, el deporte de ese día o el tipo de ticket pierden en tu historial (≥15 / ≥10 apuestas), cuando es SGM en pizarra de un solo partido, y cuando el monto pasa 2x tu mediana ($7). Lee los números en vivo del historial: si los jueves empiezan a ganar, se apaga solo. 4 pruebas nuevas.
- `/api/lint-slip` acepta `context` y por defecto manda el día de hoy (hora ET).
- Panel **"Rendimiento por día"** en Track Record, con `GET /api/stake-history/weekday?day=Thu`.

## 2. Repos revisados (clonados sin ejecutar nada, en /tmp/oss)

| Repo | Veredicto | Qué se hizo |
|---|---|---|
| **D4Vinci/Scrapling** | **Adoptado** | `scripts/inactives_feed.py`: inactivos oficiales con el parser de Scrapling (`Selector`), con respaldo regex y pruebas. Solo GET normal de una página pública; sin navegador sigiloso ni saltar anti-bots. |
| **pbakaus/impeccable** | **Adoptado (detector)** | `npx impeccable detect src`: 1 hallazgo (fuente Inter muy usada) + 4 avisos. Arreglé 3 animaciones `bounce`. Fuente y fondo de cuadrícula quedan como decisión de marca. |
| **GoogleChrome/modern-web-guidance-src** | **Usado** | `legacy-scan src`: 0 patrones viejos en 33 guías. |
| **ayghri/i-have-adhd** | **Adoptado** | Skill instalada en `.claude/skills/i-have-adhd` (MIT): acción primero, pasos numerados. Va con tu preferencia de respuestas cortas. |
| **Panniantong/Agent-Reach** | Ya instalado (2026-10-11) | Lectura de X/Reddit/YouTube para noticias de lesiones y tipsters. |
| **morluto/rea** | Ya adoptada la idea (grabador de páginas) | No hace falta el MCP de ingeniería inversa completo. |
| **anthropics/knowledge-work-plugins** | Ya instalados | finance, data, legal, etc. ya están en este entorno. |
| google-research/timesfm | Rechazado por ahora | Necesita torch; este Mac es Intel y el Python del sistema es 3.13, sin torch compatible. Además, pronosticar series no reemplaza al mercado en apuestas. |
| pathwaycom/pathway | Rechazado | Streaming tipo Kafka; nuestro volumen se cubre con scripts y caché. |
| Nutlope/hallmark | Rechazado | Duplica a impeccable. |
| Tencent/BrowserSkill | Rechazado | Duplica Claude in Chrome. |
| pingdotgg/t3code, CopilotKit/OpenBot, milind-soni/OpenMausBot, QwenLM/qwen-code | Rechazados | Interfaces/agentes de programación; no mejoran el motor de apuestas. |
| NVIDIA/OpenShell, NVIDIA/auto-ontology | Rechazados | Sandbox de agentes y ontologías empresariales; sin uso aquí. |
| Lakr233/vphone-cli, NSA/ghidra | Rechazados | iPhone virtual e ingeniería inversa; ghidra ya se rechazó en octubre. |
