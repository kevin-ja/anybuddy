# modules/events — reservado

Aquí vivirá el disparador event-driven:

- Regla **EventBridge** que escucha cambios en S3 (prefijos `knowledge_base/`, `models/` → ingesta; `vector_db/` → redeploy).
- Destino **SSM RunCommand** directo contra el EC2 (decisión tentativa: **sin Lambda**).
- **Lambda** solo si hiciera falta lógica condicional (p.ej. "según qué artefacto, correr comando distinto"); en ese caso llevaría su rol IAM con `ssm:SendCommand` y el permiso para que EventBridge la invoque.

El disparador solo *dispara*; el trabajo pesado (ingesta y `docker compose`) corre en el EC2 vía SSM.
