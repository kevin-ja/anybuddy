
# Model Loader
Contiene la logica de **cómo** descargar los modelos de embedding y re-ranker 
para cualquier servicio que los necesite.

Sus carácteristicas son:
* **Agnostico** al servicio que lo usa: El Model Loader funciona independientemente 
desde donde el modelo se descargará (Source) y donde se guadará (Sink). Dichas rutas/ubicaciones lo tiene que definir el servicio que lo use.
- **Paquete instalable** : cualquier servicio lo importa limpio (`from model_loader.embedding import ...`) sin pelearse con rutas relativas ni `sys.path`.


