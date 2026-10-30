# Asistente IA para LibreOffice

Extensión `.oxt` que añade un chat con IA a LibreOffice Writer, Calc e Impress.
Puedes pedir en español que escriba, corrija, formatee, inserte tablas, listas,
imágenes, índices y diapositivas. Los cambios se aplican como una vista previa
agrupada y tú decides si los mantienes o los deshaces.

## Requisitos

- LibreOffice 24.2 o superior (probado con 26.8).
- Una clave de API de OpenCode.
- Conexión a Internet.

No requiere Python externo ni instalar `requests`: la extensión usa el Python
incluido en LibreOffice y solo la biblioteca estándar.

## Instalación

1. Genera el paquete:

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

El archivo queda en `dist\LibreOfficeAI.oxt`.

2. Instálalo de una de estas formas:

- Abre LibreOffice, ve a **Herramientas > Extensiones**, pulsa **Añadir** y
  selecciona `dist\LibreOfficeAI.oxt`.
- O ejecuta:

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1 -Install
```

3. Reinicia LibreOffice. Aparecerá el menú **Asistente IA**.

## Configuración

Abre **Asistente IA > Ajustes...** y configura:

| Campo | Valor recomendado |
| --- | --- |
| URL base | `https://opencode.ai/inference/go/openai/v1` |
| Modelo | `deepseek-v4.1-flash` |
| Clave de API | Tu clave de OpenCode |

La URL base debe ser la raíz compatible con OpenAI. Si pegas una URL que termina
en `/chat/completions`, se recorta automáticamente. Por seguridad se exige
`https://`; solo `localhost`, `127.0.0.1` e `::1` pueden usar `http://`.

La clave se guarda en el perfil local de LibreOffice:

```text
%APPDATA%\LibreOffice\4\user\LibreOfficeAI\config.json
```

También puedes usar la variable de entorno `OPENCODE_API_KEY` si prefieres no
guardarla en el archivo. Al guardar ajustes se crea una copia
`config.json.bak` con la configuración anterior.

## Uso

1. Abre un documento de Writer, Calc o Impress.
2. Selecciona **Asistente IA > Abrir chat**. El panel aparece anclado al lado
   derecho de la pantalla.
3. Escribe la petición. Ejemplos:
   - "Corrige la ortografía del párrafo seleccionado y mejora la redacción."
   - "Crea una tabla con estos datos y pon la primera fila en negrita."
   - "Añade una diapositiva con el título 'Resultados' y tres viñetas."
   - "En la hoja activa, escribe el presupuesto desde A1 y ordena por importe."
4. Los cambios se aplican de inmediato como **vista previa** y aparecen en
   **Cambios propuestos**.
5. Pulsa **Aceptar** para mantenerlos o **Rechazar** para deshacerlos todos de
   una vez. La vista previa también se revierte al cerrar el chat, iniciar otro
   chat o enviar una petición nueva sin aceptar.
6. Si ya hiciste otros cambios después de la vista previa, **Rechazar** no
   deshace nada: la extensión comprueba que el grupo de la IA siga siendo el
   último paso del historial.

El chat mantiene el contexto de la conversación. **Nuevo chat** borra el
historial y las propuestas pendientes (revirtiendo antes la vista previa).
**Detener** cancela la espera de la petición actual; la petición de red ya
enviada puede terminar en segundo plano.

## Acciones disponibles

### Writer

- Insertar o reemplazar texto, con estilos de párrafo y encabezados.
- Reescribir la selección.
- Buscar y reemplazar.
- Insertar tablas con encabezado y estilo.
- Insertar listas con viñetas o numeradas.
- Aplicar negrita, cursiva, subrayado, fuente, tamaño, color y alineación.
- Insertar saltos de página.
- Insertar imágenes locales.
- Insertar un índice de contenido.

### Calc

- Escribir valores y fórmulas en celdas o rangos.
- Crear tablas con encabezado y formato básico.
- Insertar filas y columnas.
- Formatear rangos, colores, bordes, números y alineación.
- Ajustar el ancho de columnas.
- Ordenar rangos.
- Añadir hojas.

### Impress

- Añadir diapositivas.
- Cambiar títulos.
- Añadir cuadros de texto y viñetas.
- Insertar imágenes.
- Insertar tablas como texto tabulado (limitación de la API de Impress en esta
  versión; se insertan en un cuadro de texto alineado por tabulaciones).

## Seguridad y privacidad

- La extensión solo envía al proveedor el texto de tu petición y un resumen del
  contexto del documento (tipo, título sin ruta local, selección o párrafo
  actual, vista previa de celdas o textos de la diapositiva). No envía el
  documento completo.
- El contexto se puede desactivar con la casilla **Incluir contexto del documento**.
  Tampoco se acumula en el historial: cada petición usa solo el contexto actual.
- La URL base debe usar HTTPS. Así la clave y el contenido viajan cifrados.
- La extensión no sigue redirecciones HTTP hacia otro servidor, para no reenviar
  la clave a un destino distinto.
- La clave de API se guarda en texto plano en tu perfil local. Protégela como
  cualquier otro archivo de configuración.
- Cada conversación envía un identificador de sesión (`x-opencode-session`) para
  que el proveedor pueda enrutar la conversación.
- No se registran claves ni se incluyen en los mensajes de error.
- Las fórmulas que pueden acceder a recursos externos (`WEBSERVICE`,
  `HYPERLINK`, `DDE`, `IMPORTXML`, `IMPORTHTML`, `IMPORTDATA`, `IMPORTFEED`,
  `RTD`) se bloquean antes de escribir en la hoja y se muestran en la vista
  previa.
- Las imágenes deben ser archivos locales existentes, con formato de imagen
  conocido y menos de 20 MB. Se rechazan rutas UNC y URL.
- La vista previa se ejecuta antes de que pulses Aceptar. Esto es intencionado:
  puedes ver el resultado real en el documento. Rechazar deshace el grupo; si
  algo falla, la extensión intenta revertir y avisa si no pudo hacerlo.

## Desarrollo

Estructura principal:

```text
extension/
  Addons.xcu, ProtocolHandler.xcu, description.xml, META-INF/manifest.xml
  pythonpath/
    main.py                 Entrada UNO y manejador del menú
    core/                   Configuración, LLM, agente, herramientas y ejecución
    core/adapters/          Writer, Calc e Impress
    ui/                     Diálogos nativos de chat y ajustes
tests/                      Pruebas unitarias sin red ni LibreOffice
build.ps1                   Empaquetado .oxt
```

Comprobaciones:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q extension\pythonpath
```

Para probar la extensión en un perfil temporal de LibreOffice:

```powershell
& "C:\Program Files\LibreOffice\program\unopkg.com" add -env:UserInstallation=file:///C:/Temp/lo-ai-profile dist\LibreOfficeAI.oxt
```

## Solución de problemas

- **No aparece el menú**: reinicia LibreOffice y comprueba que la extensión esté
  activa en **Herramientas > Extensiones**.
- **Falta la clave de API**: abre Ajustes y pégala, o define `OPENCODE_API_KEY`
  antes de iniciar LibreOffice.
- **Error 401/403**: la clave no es válida o la suscripción de OpenCode Go no
  incluye el modelo elegido.
- **Error 404**: revisa la URL base y el nombre del modelo.
- **Error 429**: espera un momento; se alcanzó el límite de peticiones.
- **No hay documento activo**: abre un documento Writer, Calc o Impress antes de
  enviar la petición.
- **No se puede rechazar**: probablemente hiciste cambios después de la vista
  previa. Deshaz manualmente o acepta la vista previa.
- **Un cambio no se aplica**: revisa el mensaje de error del chat. La ejecución
  se cancela y se intenta deshacer el grupo completo si una acción falla.

## Limitaciones conocidas

- La interfaz es un diálogo flotante nativo, no una barra lateral.
- No hay streaming token a token: la respuesta aparece al terminar.
- El contexto es un resumen; para documentos muy grandes no se envía todo.
- Las tablas de Impress usan texto tabulado, no una tabla nativa.
- Las operaciones se ejecutan en el hilo principal de LibreOffice; las peticiones
  de red se hacen en un hilo aparte.

## Licencia

MIT. Consulta `extension/registration/license.txt`.
