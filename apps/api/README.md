### Flujo
1. **Alumno** escribe un mensaje en Discord.  
2. **Servidor Discord** lo reenvía al `discord_bot.py` mediante WebSocket.  
3. **discord_bot.py** empaqueta el mensaje y hace una petición HTTP POST a **FastAPI**.  
4. **FastAPI** recibe la petición e invoca internamente a **LangGraph** (en memoria RAM).  
5. **LangGraph** procesa el mensaje usando el LLM y las herramientas, y devuelve el texto final a **FastAPI**.  
6. **FastAPI** responde a `discord_bot.py` con un HTTP 200 y la respuesta en JSON.  
7. **discord_bot.py** extrae el texto y utiliza el comando `await message.reply()` para enviarlo de vuelta al servidor de Discord.  
8. **Servidor Discord** publica la respuesta y el **Alumno** la ve en su pantalla.

> **Nota:** FastAPI nunca se comunica directamente con Discord. `discord_bot.py` actúa como puente o “embajador” ante Discord, lo que permite mantener una arquitectura limpia y desacoplada dentro del mismo entorno (por ejemplo, en AWS).


```mermaid
%%{init: {
  "theme": "dark",
  "themeVariables": {
    "background": "#373333",

    "primaryColor": "#111111",
    "primaryTextColor": "#ffffff",

    "primaryBorderColor": "#00FFFF",

    "lineColor": "#FF00FF",

    "actorBorder": "#39FF14",
    "actorBkg": "#111111",
    "actorTextColor": "#ffffff",

    "signalColor": "#00FFFF",
    "signalTextColor": "#ffffff",

    "labelBoxBkgColor": "#111111",
    "labelBoxBorderColor": "#6f47ff",

    "noteBorderColor": "#FF00FF",
    "noteBkgColor": "#111111"
  }
}}%%

sequenceDiagram
    participant Alumno
    participant DiscordServer as Servidor Discord
    participant DiscordBot as discord_bot.py
    participant FastAPI
    participant LangGraph

    Alumno->>DiscordServer: Escribe un mensaje en el canal
    DiscordServer->>DiscordBot: Envía el mensaje vía WebSocket
    Note over DiscordBot: Recibe el texto y lo empaqueta
    DiscordBot->>FastAPI: HTTP POST (JSON con el mensaje)
    FastAPI->>LangGraph: Invoca internamente (en RAM) con el prompt
    Note over LangGraph: Procesa con LLM y herramientas
    LangGraph-->>FastAPI: Devuelve el texto de respuesta
    FastAPI-->>DiscordBot: HTTP 200 OK (respuesta en JSON)
    Note over DiscordBot: Extrae el texto y usa await message.reply()
    DiscordBot->>DiscordServer: Envía la respuesta vía WebSocket
    DiscordServer-->>Alumno: Muestra la respuesta en el canal
```

# estructura


