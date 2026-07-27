# Arcus — Dashboard

![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![Vite](https://img.shields.io/badge/Vite-5-646CFF?logo=vite&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-3-38BDF8?logo=tailwindcss&logoColor=white)
![Recharts](https://img.shields.io/badge/Charts-Recharts-22B5BF)

**Español** · [English](README.en.md)

Interfaz web del proyecto [Arcus](../README.md). Este README cubre únicamente el frontend
que vive en la carpeta `dashboard/`.

---

## Descripción general

El **Repo Health Dashboard** es una SPA (Single Page Application) de **solo lectura** que
visualiza los resultados que produce el pipeline de revisión de PRs de Arcus. Muestra la
salud de cada repositorio a lo largo del tiempo: revisiones ejecutadas, hallazgos por
severidad y tipo, fiabilidad de cada agente, actividad reciente y el grafo de contexto del
repositorio.

**Propósito dentro de Arcus.** El backend (webhook → Step Functions → 5 agentes) analiza
cada Pull Request y persiste el resultado en DynamoDB. El dashboard **consume** esos datos y
los presenta de forma legible; **nunca escribe** en DynamoDB ni en S3. Este límite es
intencional: al ser solo lectura, el frontend puede desarrollarse de forma independiente y
no bloquea al resto del sistema.

**A quién está dirigido.** A mantenedores y líderes técnicos que quieren una vista agregada
de la calidad del código de sus repositorios, y al equipo de Arcus para demostrar y depurar
el comportamiento del pipeline.

> **Estado actual:** el dashboard funciona hoy contra una **capa de datos simulados**
> (determinista) que imita el esquema real de DynamoDB, por lo que es completamente
> navegable sin un backend desplegado. La conexión a la API real de solo lectura es un
> intercambio localizado de la fuente de datos (ver [Conexión con el backend / API](#conexión-con-el-backend--api)).

---

## Tecnologías y frameworks

| Área | Tecnología |
|---|---|
| Librería UI | **React 18** |
| Build tool / dev server | **Vite 5** |
| Lenguaje | **TypeScript 5** (modo estricto) |
| Estilos | **Tailwind CSS 3** (dark mode por clase, tokens vía CSS variables) |
| Gráficos | **Recharts** |
| Grafo interactivo | **react-force-graph-2d** |
| Iconos | **lucide-react** |
| Componentes accesibles | **@radix-ui/react-switch** |
| Utilidades de fecha | **date-fns** |
| Linting | **ESLint** |

Puntos técnicos destacables:
- **Carga diferida por página** (`React.lazy` + `Suspense`): cada pantalla y sus
  dependencias pesadas (Recharts, react-force-graph-2d) se descargan solo al navegar a
  ellas, manteniendo ligero el bundle inicial.
- **Alias de importación** `@/` → `src/` (configurado en `vite.config.ts` y `tsconfig.json`).
- **Theming** claro/oscuro basado en variables CSS resueltas por Tailwind.

---

## Estructura de la carpeta

```
dashboard/
├── index.html                 # Punto de entrada HTML
├── package.json               # Dependencias y scripts
├── vite.config.ts             # Config de Vite (plugin React, alias @, puerto 5173)
├── tailwind.config.js         # Tema (colores por CSS vars, fuentes, animaciones)
├── postcss.config.js          # PostCSS + Autoprefixer
├── tsconfig*.json             # Configuración de TypeScript
├── .env.example               # Variables VITE_* de solo presentación
├── public/                    # Activos estáticos (favicon, etc.)
└── src/
    ├── main.tsx               # Bootstrap de React (monta <App/>)
    ├── App.tsx                # Layout raíz: Sidebar + enrutado por página + providers
    ├── index.css              # Estilos base y tokens del tema
    ├── pages/                 # Una vista por pantalla
    │   ├── OverviewPage.tsx   #   KPIs y salud general
    │   ├── ActivityPage.tsx   #   Actividad reciente / ejecución simulada
    │   ├── GraphPage.tsx      #   Grafo de contexto del repositorio
    │   ├── FindingsPage.tsx   #   Hallazgos filtrables
    │   └── SettingsPage.tsx   #   Configuración (solo lectura del backend)
    ├── components/            # Componentes reutilizables de UI
    │   ├── charts/            #   Gráficos con Recharts (severidad, tipos, tiempo…)
    │   ├── ui/                #   Primitivas y previews
    │   ├── Sidebar.tsx, Header.tsx, KpiCard.tsx, FindingCard.tsx, GraphView.tsx …
    ├── state/                 # Estado global vía React Context
    │   ├── StoreProvider.tsx  #   Datos (runs, findings, settings) + persistencia local
    │   └── ThemeProvider.tsx  #   Tema claro/oscuro
    └── lib/                   # Lógica y datos (sin JSX)
        ├── types.ts           #   Tipos del dominio (ReviewRun, Finding, Severity…)
        ├── mockData.ts        #   Generador determinista con el shape real de DynamoDB
        ├── mockGraph.ts       #   Grafo de ejemplo para GraphPage
        ├── simulate.ts        #   Flujo de "revisión" simulada con logs
        ├── selectors.ts       #   Derivaciones/agregaciones para los gráficos
        ├── runtimeConfig.ts   #   Región y modelo (display-only, con fallback)
        └── theme.ts           #   Helpers de tema
```

Organización en tres capas: **`pages/`** ensambla pantallas, **`components/`** aporta piezas
de UI reutilizables, y **`lib/`** concentra tipos, datos y lógica pura fácil de testear y de
sustituir por la API real.

---

## Requisitos previos

- **Node.js 18 o superior** (Vite 5 requiere Node 18+; se recomienda una versión LTS).
- **npm** (el repositorio incluye `package-lock.json`). También puedes usar `pnpm` o `yarn`
  si prefieres, adaptando los comandos.

Verifica tu versión:

```bash
node -v
npm -v
```

---

## Guía de instalación y ejecución local

Todos los comandos se ejecutan **dentro de la carpeta `dashboard/`**.

```bash
# 1. Entrar a la carpeta del frontend
cd dashboard

# 2. Instalar dependencias
npm install

# 3. Levantar el servidor de desarrollo (Vite, con HMR)
npm run dev
```

Vite servirá la app en **http://localhost:5173** (el puerto está fijado en
`vite.config.ts`; `host: true` la expone también en la red local).

**Otros scripts disponibles:**

```bash
npm run build     # Type-check (tsc -b) + build de producción en dist/
npm run preview   # Sirve localmente el build de producción para verificarlo
npm run lint      # ESLint sobre archivos .ts / .tsx
```

**Variables de entorno (opcional).** Solo se usan para mostrar valores de referencia; no
son secretas. Crea un `.env.local` (o `.env`) a partir del ejemplo:

```bash
cp .env.example .env.local
```

```bash
VITE_ARCUS_AWS_REGION=us-east-1
VITE_ARCUS_BEDROCK_MODEL_ID=us.amazon.nova-2-lite-v1:0
```

Al ser variables de Vite, deben llevar el prefijo `VITE_` para estar disponibles en el
cliente, y un cambio requiere reiniciar el servidor de desarrollo.

---

## Conexión con el backend / API

El dashboard está diseñado para consumir una **API HTTP de solo lectura** respaldada por la
tabla DynamoDB `arcus-{env}-review-history`, donde el pipeline persiste cada revisión
(estado por agente, resumen de hallazgos por severidad/tipo, enlace al comentario del PR,
timestamp, etc.).

**Cómo funciona hoy (modo simulado):**
- La fuente de datos es `src/lib/mockData.ts`, que genera un dataset **determinista** con el
  **mismo shape** que devolverá la API real (el esquema definido en el diseño del backend).
  Así la UI se ve y se comporta como en producción sin depender del pipeline en vivo.
- El estado global vive en `src/state/StoreProvider.tsx` y se **persiste en `localStorage`**
  entre recargas. `src/lib/simulate.ts` permite disparar una "revisión" simulada con logs en
  vivo para la demo.

**Cómo se conectará a la API real:**
- Toda la lectura de datos pasa por el *store*, de modo que cambiar de datos simulados a la
  API real es sustituir la fuente de datos por un cliente HTTP que consulte el endpoint de
  solo lectura, conservando los mismos tipos de `src/lib/types.ts`.
- El dashboard **solo lee**: nunca escribe en DynamoDB ni en S3.

**Configuración propiedad del backend.** Valores como la **región de AWS**, el
**`BEDROCK_MODEL_ID`**, el **App ID de GitHub** y si el **webhook está configurado** son
propiedad del backend desplegado, no del navegador. En `StoreProvider` estos campos se
**fuerzan** al valor actual de runtime (`src/lib/runtimeConfig.ts`) en lugar de leerse de un
guardado previo en `localStorage`. Las variables `VITE_ARCUS_*` son solo un *fallback* de
presentación para el dashboard autónomo; la fuente de verdad sigue siendo el backend.

Para desplegar el backend que alimentará esta API, consulta el
[README principal del proyecto](../README.md).
