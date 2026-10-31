# Asistente IA para LibreOffice

Extensión `.oxt` que añade un chat con IA a LibreOffice Writer, Calc e Impress.
Puedes pedir en español que escriba, corrija, formatee, inserte tablas, listas,
imágenes, índices y diapositivas. Los cambios se aplican como una vista previa
agrupada y tú decides si los mantienes o los deshaces.

También puede revisar carpetas locales en busca de imágenes y buscar
información o imágenes en Internet, siempre que esas funciones estén activadas
en Ajustes.

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

Puedes mostrar u ocultar la clave con **Mostrar/Ocultar** y comprobar la URL, la
clave y el modelo con **Probar conexión** antes de guardar.

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

### Acceso a carpetas e Internet

En Ajustes hay dos casillas independientes:

- **Permitir listar imágenes de carpetas locales**: deja que el asistente use
  `list_local_images` para encontrar imágenes. Solo se envían al modelo nombres,
  rutas y tamaños de archivos de imagen compatibles; no se lee ni se envía su
  contenido.
- **Permitir búsquedas y descargas desde Internet**: habilita las herramientas
  `search_web`, `search_images`, `fetch_web_page` y `download_image`.

Puedes desactivar cualquiera de las dos si no quieres que el modelo acceda a esa
información.

## Uso

1. Abre un documento de Writer, Calc o Impress.
2. Selecciona **Asistente IA > Abrir chat**. El panel aparece anclado al lado
   derecho de la pantalla.
3. Escribe la petición. Ejemplos:
   - "Corrige la ortografía del párrafo seleccionado y mejora la redacción."
   - "Crea una tabla con estos datos y pon la primera fila en negrita."
   - "Añade una diapositiva con el título 'Resultados' y tres viñetas."
   - "En la hoja activa, escribe el presupuesto desde A1 y ordena por importe."
   - "Revisa la carpeta Pictures\Mac aleatoria e inserta las imágenes que
     encajen en el apartado de imágenes."
   - "Busca información actual sobre X y añade un resumen con las fuentes."
4. Pulsa **Ctrl+Enter** para enviar; **Enter** añade una línea nueva.
5. Los cambios se aplican de inmediato como **vista previa** y aparecen en
   **Cambios propuestos**, con una casilla por acción.
6. Pulsa **Aceptar** para mantener las acciones marcadas o **Rechazar** para
   deshacerlas todas de una vez. Si dejas casillas sin marcar, solo se conservan
   las seleccionadas. La vista previa también se revierte al cerrar el chat,
   iniciar otro chat o enviar una petición nueva sin aceptar.
7. Si ya hiciste otros cambios después de la vista previa, **Rechazar** no
   deshace nada: la extensión comprueba que el grupo de la IA siga siendo el
   último paso del historial.

El chat mantiene el contexto de la conversación. **Nuevo chat** borra el
historial y las propuestas pendientes (revirtiendo antes la vista previa).
**Detener** cancela la espera de la petición actual; la petición de red ya
enviada puede terminar en segundo plano.

## Carpetas locales e Internet

El asistente ejecuta estas consultas en segundo plano, sin bloquear el
documento, y después usa el resultado para proponer cambios:

- `list_local_images`: lista imágenes de una carpeta (por defecto, `Pictures`).
  Admite búsqueda recursiva y un límite de resultados. Rechaza rutas de red y
  archivos que no sean imágenes compatibles.
- `search_web`: busca en la web y devuelve título, URL y resumen.
- `search_images`: busca imágenes y devuelve URLs directas.
- `fetch_web_page`: lee el texto de una página pública.
- `download_image`: descarga una imagen pública a una carpeta temporal y
  devuelve la ruta local para insertarla en el documento.

Las URLs de Internet se validan antes de abrirlas. Solo se permiten `http://` o
`https://` en los puertos 80 y 443, y se bloquean `localhost`, direcciones
privadas, enlaces locales y redirecciones a otros hosts. Las imágenes
descargadas se limitan a 20 MB y se guardan en la carpeta temporal del sistema.

## Acciones disponibles

### Writer

- Insertar o reemplazar texto, con estilos de párrafo y encabezados.
- Reescribir la selección.
- Buscar y reemplazar.
- Insertar tablas con encabezado y estilo.
- Insertar listas con viñetas o numeradas.
- Aplicar negrita, cursiva, subrayado, fuente, tamaño, color y alineación.
- Insertar saltos de página.
- Insertar imágenes locales, incluidas las descargadas desde Internet.
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

- Añadir diapositivas con disposición título, título y contenido, solo título o
  en blanco.
- Cambiar títulos y rellenar las áreas de título y contenido.
- Añadir cuadros de texto y viñetas.
- Insertar imágenes locales o descargadas.
- Insertar tablas nativas de Impress. Si la versión de LibreOffice no puede
  crearlas, se usa un cuadro de texto alineado por tabulaciones como respaldo.

## Seguridad y privacidad

- La extensión solo envía al proveedor el texto de tu petición y un resumen del
  contexto del documento (tipo, título sin ruta local, selección o párrafo
  actual, vista previa de celdas o textos de la diapositiva). No envía el
  documento completo.
- El contexto se puede desactivar con la casilla **Incluir contexto del documento**.
  Tampoco se acumula en el historial: cada petición usa solo el contexto actual.
- Si activas el acceso a carpetas, el modelo recibe nombres, rutas y tamaños de
  las imágenes encontradas. No recibe el contenido de los archivos.
- Si activas Internet, tus consultas y las URLs consultadas se envían a los
  buscadores públicos y a los sitios web correspondientes. La clave de OpenCode
  no se envía a esos sitios.
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
  `RTD`, `INDIRECT`), las referencias externas y las fórmulas sin `=` que
  LibreOffice interpretaría se bloquean antes de escribir en la hoja. Las
  fórmulas permitidas se muestran en la vista previa.
- Las imágenes deben ser archivos locales existentes, con formato de imagen
  conocido y menos de 20 MB. Se rechazan rutas UNC y URL al insertar; para una
  imagen de Internet, primero se descarga a una ruta local temporal.
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
    core/web.py             Búsqueda, lectura y descarga con protecciones SSRF
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
- **No encuentra imágenes en una carpeta**: comprueba la ruta y que los archivos
  tengan un formato compatible (`.png`, `.jpg`, `.jpeg`, `.gif`, `.bmp`, `.svg`,
  `.webp`, `.tif` o `.tiff`). La búsqueda recursiva está limitada a cinco niveles.
- **La búsqueda web no devuelve resultados**: el buscador público puede estar
  bloqueando la petición. Prueba otra consulta o vuelve a intentarlo más tarde.
- **Un cambio no se aplica**: revisa el mensaje de error del chat. La ejecución
  se cancela y se intenta deshacer el grupo completo si una acción falla.

## Limitaciones conocidas

- La interfaz es un panel flotante nativo anclado a la derecha, no una barra
  lateral integrada.
- No hay streaming token a token: la respuesta aparece al terminar.
- El contexto es un resumen; para documentos muy grandes no se envía todo.
- La búsqueda web y de imágenes depende de buscadores públicos y puede fallar si
  cambian su formato o bloquean peticiones automatizadas.
- La vista previa se ejecuta antes de Aceptar; si otra persona edita el
  documento después, puede que ya no sea posible rechazarla automáticamente.
- Las operaciones se ejecutan en el hilo principal de LibreOffice; las peticiones
  de red se hacen en un hilo aparte.

## Licencia

MIT. Consulta `extension/registration/license.txt`.
