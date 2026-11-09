# 📖 Manual de uso — Centinela Vial

**Tu copiloto de monitoreo vial en Telegram para transporte de carga en México.**

Este manual es para el **operador**: cómo usar el bot día a día. Si buscas la parte
técnica (instalación, despliegue), revisa el `README.md`.

---

## 1. ¿Qué es Centinela Vial?

Es un bot de Telegram que **vigila tu ruta** y te avisa de lo que puede afectar tu
viaje: accidentes, carreteras cerradas, tráfico pesado, clima peligroso y noticias
de seguridad. Tú le dices a dónde vas y él se encarga de alertarte.

**Dos formas de recibir información:**
- 🔔 **Alertas automáticas:** una vez que inicias un viaje, el bot revisa tu ruta
  cada 30 minutos y te avisa si surge algo nuevo.
- 💬 **Consultas al momento:** escribe un comando y te responde con la situación actual.

---

## 2. Primeros pasos

1. Abre una conversación con el bot en Telegram.
2. Escribe `/start` para ver la lista de comandos.
3. Inicia tu primer viaje:

   ```
   /viaje CDMX - Monterrey
   ```

   El bot calcula la ruta, te muestra distancia, tiempo, las ciudades por las que
   pasa y las regiones que vigilará. A partir de ahí, **recibirás alertas automáticas**.

> 💡 Puedes escribir el origen y destino de varias formas: `CDMX - Monterrey`,
> `CDMX → Monterrey`, `CDMX a Monterrey`.

---

## 3. Comandos, uno por uno

### 🚦 Monitoreo de tu viaje

| Comando | Para qué sirve | Ejemplo |
|---|---|---|
| `/viaje ORIGEN - DESTINO` | Inicia el monitoreo de una ruta | `/viaje Guadalajara - Querétaro` |
| `/alertas` | Muestra los incidentes en tu ruta **ahora mismo** | `/alertas` |
| `/trafico` | Estado del tráfico y demoras en tu ruta | `/trafico` |
| `/ruta` | Desglose de la ruta: tramos, carreteras, km y tiempo | `/ruta` |
| `/estado` | Resumen de tu viaje activo | `/estado` |
| `/regiones` | Regiones y estados que cubre tu ruta | `/regiones` |
| `/detener` | Termina el monitoreo del viaje | `/detener` |

### 🛰 Escaneos y noticias (no requieren viaje activo)

| Comando | Para qué sirve |
|---|---|
| `/escaneo` | Panorama vial de las carreteras nacionales clave |
| `/zona` | Reporte del corredor ZMVM Norte (Neza, Ecatepec, Coacalco, Tlalnepantla, Tecámac, Tultitlán, Cuautitlán) |
| `/rcpn` | Noticias recientes de Resistencia Civil Pacífica Nacional (últimos 30 días) |

### 🤖 Preguntas en lenguaje natural

Escribe cualquier pregunta **sin `/`** y el asistente de IA te responde usando los
datos de tu ruta activa. Ejemplos:

```
¿Cómo está el clima rumbo a Monterrey?
¿Hay algún cierre en mi ruta?
¿Cuánto me falta para llegar?
```

---

## 4. Cómo leer las alertas

Las alertas usan íconos para que las entiendas de un vistazo:

| Ícono | Significa |
|---|---|
| 🚨 | Incidente crítico (accidente, cierre) |
| ✅ | Carretera **reabierta** (buena noticia) |
| 🚦 / 🟠 / 🔴 | Flujo vial: lento / muy lento |
| 🌦 / 🌧 | Clima adverso en la ruta |
| 📰 | Noticia o aviso vial |
| 📍 | Enlace al punto exacto en Google Maps |

El bot **no te repite** la misma alerta: una vez que te avisó de un incidente, no
vuelve a mandártelo (a menos que reaparezca pasadas unas horas).

---

## 5. Preguntas frecuentes

**¿Cada cuánto me avisa?**
Las alertas de tu ruta se revisan cada **30 minutos**. Los comandos que escribes se
procesan en **≤5 minutos**. Si un comando tarda un poco, es normal: el bot no está
encendido todo el tiempo, revisa por ciclos (así es gratis de operar).

**Escribí un comando y no responde de inmediato.**
Espera unos minutos. El bot agrupa los mensajes y responde en el siguiente ciclo.

**¿Puedo tener varios viajes a la vez?**
Cada chat vigila **un viaje activo**. Si inicias uno nuevo, reemplaza al anterior.
Usa `/detener` cuando termines para dejar de recibir alertas.

**¿El bot guarda mis rutas o datos?**
Sólo guarda lo mínimo para funcionar: tu viaje activo y qué alertas ya te envió.
**No** almacena históricos, datos de clientes, placas ni información sensible.

**¿`/rcpn` es información oficial?**
No. Son noticias de terceros agregadas de Google News. El propio bot te muestra un
aviso: verifica siempre la fuente original antes de compartir.

---

## 6. Consejos de uso

- Inicia el `/viaje` **antes de salir**: así el bot ya está vigilando desde el arranque.
- Usa `/alertas` y `/trafico` en las paradas para decidir si cambias de ruta u horario.
- Usa `/zona` si operas en el corredor EdoMex→CDMX; da el detalle municipio por municipio.
- Al terminar, `/detener` para no seguir recibiendo avisos de una ruta que ya no usas.

---

*Centinela Vial — proyecto educativo de monitoreo de seguridad vial. Úsalo con
responsabilidad y verifica siempre la información crítica con fuentes oficiales.*
