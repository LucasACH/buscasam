/* ============================================================
   BUSCASAM — Sample data (realistic UNSAM academic content)
   Attaches to window.DATA
   ============================================================ */
window.DATA = (function () {

  const user = {
    name: "Sofía Maldonado",
    email: "smaldonado@estudiantes.unsam.edu.ar",
    role: "Estudiante",
    initials: "SM",
  };

  // Cascade: Escuela › Carrera › Materia
  const areas = [
    {
      escuela: "Escuela de Ciencia y Tecnología",
      short: "ECyT",
      carreras: [
        { carrera: "Ingeniería en Bioinformática", materias: ["Aprendizaje automático", "Bases de datos biológicas", "Procesamiento de imágenes"] },
        { carrera: "Licenciatura en Ciencia de Datos", materias: ["Estadística aplicada", "Redes neuronales", "Minería de datos"] },
        { carrera: "Ingeniería Ambiental", materias: ["Contaminación de aguas", "Gestión de residuos"] },
      ],
    },
    {
      escuela: "Instituto de Investigaciones Biotecnológicas",
      short: "IIB",
      carreras: [
        { carrera: "Licenciatura en Biotecnología", materias: ["Biología molecular", "Microbiología", "Inmunología"] },
        { carrera: "Doctorado en Biología", materias: ["Genética", "Bioquímica avanzada"] },
      ],
    },
    {
      escuela: "Escuela de Humanidades",
      short: "EH",
      carreras: [
        { carrera: "Licenciatura en Filosofía", materias: ["Filosofía política", "Epistemología"] },
        { carrera: "Profesorado en Historia", materias: ["Historia argentina", "Historia contemporánea"] },
      ],
    },
    {
      escuela: "Escuela de Economía y Negocios",
      short: "EEyN",
      carreras: [
        { carrera: "Licenciatura en Economía", materias: ["Macroeconomía", "Econometría"] },
        { carrera: "Contador Público", materias: ["Finanzas corporativas"] },
      ],
    },
    {
      escuela: "Escuela de Política y Gobierno",
      short: "EPyG",
      carreras: [
        { carrera: "Ciencia Política", materias: ["Políticas públicas", "Teoría del Estado"] },
      ],
    },
    {
      escuela: "Escuela de Hábitat y Sostenibilidad",
      short: "EHyS",
      carreras: [
        { carrera: "Ingeniería Ambiental Urbana", materias: ["Urbanismo sostenible", "Recursos hídricos"] },
      ],
    },
  ];

  const tipos = [
    "Tesis", "Tesina", "Paper", "Trabajo práctico",
    "Monografía", "Informe técnico", "Proyecto final", "Artículo de conferencia",
  ];

  const docs = [
    {
      id: "d_8f2a1c",
      title: "Detección temprana de mal de Chagas mediante visión por computadora",
      authors: ["M. Rodríguez", "J. Pérez", "L. Gómez"],
      year: 2024,
      escuela: "Escuela de Ciencia y Tecnología",
      carrera: "Ingeniería en Bioinformática",
      materia: "Procesamiento de imágenes",
      tipo: "Tesis",
      visibility: "interno",
      keywords: ["visión por computadora", "Chagas", "diagnóstico", "aprendizaje profundo"],
      abstract: "Se presenta un sistema de visión por computadora para asistir en el diagnóstico temprano del mal de Chagas a partir de imágenes de microscopía. Entrenado sobre un conjunto de 12.400 muestras anotadas por especialistas del Hospital El Cruce, el modelo alcanza una sensibilidad del 94,2% y una especificidad del 91,8%, superando a los métodos de referencia basados en conteo manual. El trabajo discute además el sesgo de muestreo y la transferencia del modelo a equipos de bajo costo.",
      snippet: "Se presenta un sistema de <mark>visión por computadora</mark> para asistir en el diagnóstico temprano del mal de Chagas a partir de imágenes de microscopía.",
    },
    {
      id: "d_3b9e07",
      title: "Modelos de lenguaje para corpus en español rioplatense",
      authors: ["A. Ferreyra", "C. Bianchi"],
      year: 2025,
      escuela: "Escuela de Ciencia y Tecnología",
      carrera: "Licenciatura en Ciencia de Datos",
      materia: "Redes neuronales",
      tipo: "Paper",
      visibility: "publico",
      keywords: ["NLP", "español rioplatense", "modelos de lenguaje", "corpus"],
      abstract: "Este trabajo construye un corpus anotado de 2,1 millones de oraciones del español rioplatense y evalúa el desempeño de modelos de lenguaje preentrenados frente a variantes regionales. Los resultados muestran una caída sistemática de rendimiento en voseo y léxico local, y proponemos una estrategia de ajuste fino que recupera 6 puntos de F1 en tareas de análisis de sentimiento.",
      snippet: "…proponemos una estrategia de ajuste fino para <mark>modelos de lenguaje</mark> que recupera 6 puntos de F1 en tareas de análisis de sentimiento sobre español rioplatense.",
    },
    {
      id: "d_5c1f88",
      title: "Estudio de microplásticos en la cuenca del Río Reconquista",
      authors: ["P. Sosa", "R. Medina", "F. Aguirre", "T. Núñez"],
      year: 2023,
      escuela: "Escuela de Hábitat y Sostenibilidad",
      carrera: "Ingeniería Ambiental Urbana",
      materia: "Recursos hídricos",
      tipo: "Informe técnico",
      visibility: "publico",
      keywords: ["microplásticos", "Río Reconquista", "contaminación", "agua"],
      abstract: "Se cuantifica la presencia de microplásticos en 18 puntos de muestreo a lo largo de la cuenca del Río Reconquista durante un ciclo anual. Las concentraciones máximas se registran aguas abajo de los polos industriales, con predominio de fibras de poliéster. El informe propone un protocolo de monitoreo de bajo costo replicable por municipios.",
      snippet: "Se cuantifica la presencia de <mark>microplásticos</mark> en 18 puntos de muestreo a lo largo de la cuenca del Río Reconquista durante un ciclo anual.",
    },
    {
      id: "d_7a44d2",
      title: "Optimización de rutas de recolección de residuos urbanos con algoritmos genéticos",
      authors: ["D. Ledesma"],
      year: 2024,
      escuela: "Escuela de Hábitat y Sostenibilidad",
      carrera: "Ingeniería Ambiental Urbana",
      materia: "Urbanismo sostenible",
      tipo: "Proyecto final",
      visibility: "publico",
      keywords: ["algoritmos genéticos", "logística", "residuos", "optimización"],
      abstract: "Se modela la recolección de residuos del partido de San Martín como un problema de ruteo de vehículos con ventanas temporales y se resuelve mediante un algoritmo genético con operadores específicos del dominio. La solución propuesta reduce un 17% la distancia total recorrida frente a las rutas actuales.",
      snippet: "…se resuelve mediante un <mark>algoritmo genético</mark> que reduce un 17% la distancia total recorrida frente a las rutas actuales de recolección.",
    },
    {
      id: "d_2e90b5",
      title: "Caracterización de cepas probióticas aisladas de productos lácteos artesanales",
      authors: ["V. Romero", "G. Castro"],
      year: 2023,
      escuela: "Instituto de Investigaciones Biotecnológicas",
      carrera: "Licenciatura en Biotecnología",
      materia: "Microbiología",
      tipo: "Tesina",
      visibility: "publico",
      keywords: ["probióticos", "microbiología", "lactobacilos", "fermentación"],
      abstract: "Se aislaron y caracterizaron 34 cepas de bacterias lácticas a partir de quesos artesanales de la provincia de Buenos Aires. Cinco cepas mostraron actividad probiótica relevante in vitro, con tolerancia a pH gástrico y capacidad de adhesión epitelial, posicionándose como candidatas para desarrollos alimentarios funcionales.",
      snippet: "Cinco <mark>cepas</mark> mostraron actividad probiótica relevante in vitro, con tolerancia a pH gástrico y capacidad de adhesión epitelial.",
    },
    {
      id: "d_9d12af",
      title: "El concepto de soberanía en el pensamiento político argentino (1880–1930)",
      authors: ["M. Iturralde"],
      year: 2022,
      escuela: "Escuela de Humanidades",
      carrera: "Licenciatura en Filosofía",
      materia: "Filosofía política",
      tipo: "Monografía",
      visibility: "publico",
      keywords: ["soberanía", "pensamiento político", "Argentina", "siglo XX"],
      abstract: "La monografía rastrea las transformaciones del concepto de soberanía en el debate político argentino entre 1880 y 1930, atendiendo a la tensión entre soberanía popular y razón de Estado en autores del período. Se argumenta que la noción se desplaza progresivamente hacia una legitimación técnico-administrativa.",
      snippet: "…rastrea las transformaciones del concepto de <mark>soberanía</mark> en el debate político argentino entre 1880 y 1930.",
    },
    {
      id: "d_4f81c0",
      title: "Impacto de la política monetaria sobre la inversión en pymes industriales",
      authors: ["E. Quiroga", "S. Domínguez"],
      year: 2025,
      escuela: "Escuela de Economía y Negocios",
      carrera: "Licenciatura en Economía",
      materia: "Macroeconomía",
      tipo: "Paper",
      visibility: "interno",
      keywords: ["política monetaria", "pymes", "inversión", "tasa de interés"],
      abstract: "Mediante un panel de 1.200 pymes industriales del conurbano bonaerense, se estima el efecto de cambios en la tasa de política monetaria sobre las decisiones de inversión. Los resultados sugieren una elasticidad negativa significativa, amplificada en empresas con mayor restricción crediticia.",
      snippet: "…se estima el efecto de cambios en la <mark>tasa de política monetaria</mark> sobre las decisiones de inversión de pymes industriales.",
    },
    {
      id: "d_6b23e9",
      title: "Trabajo práctico: clasificación de imágenes satelitales con redes convolucionales",
      authors: ["Sofía Maldonado"],
      year: 2024,
      escuela: "Escuela de Ciencia y Tecnología",
      carrera: "Licenciatura en Ciencia de Datos",
      materia: "Redes neuronales",
      tipo: "Trabajo práctico",
      visibility: "privado",
      keywords: ["CNN", "teledetección", "clasificación", "satélite"],
      abstract: "Trabajo práctico de la materia Redes Neuronales: se entrena una red convolucional para clasificar cobertura del suelo a partir de imágenes Sentinel-2 sobre la región metropolitana. Se comparan tres arquitecturas y se reporta una precisión global del 88%.",
      snippet: "Se entrena una red <mark>convolucional</mark> para clasificar cobertura del suelo a partir de imágenes Sentinel-2 sobre la región metropolitana.",
    },
  ];

  const notifications = [
    {
      id: "n1", kind: "coauthor_invite", read: false, time: "hace 12 min",
      inviter: "Carla Bianchi",
      doc: "Modelos de lenguaje para corpus en español rioplatense",
    },
    {
      id: "n2", kind: "document_hidden", read: false, time: "hace 3 h",
      doc: "Estudio de microplásticos en la cuenca del Río Reconquista",
      reason: "Posible duplicado de un trabajo ya publicado.",
    },
    {
      id: "n3", kind: "processing_failed", read: true, time: "ayer",
      doc: "Optimización de rutas de recolección de residuos urbanos",
    },
    {
      id: "n4", kind: "document_unhidden", read: true, time: "hace 2 días",
      doc: "El concepto de soberanía en el pensamiento político argentino",
      reason: "Revisado por el equipo de moderación.",
    },
  ];

  // Registered UNSAM users (for the coautor picker)
  const people = [
    { id: "u1", name: "Carla Bianchi", email: "cbianchi@unsam.edu.ar" },
    { id: "u2", name: "Andrés Ferreyra", email: "aferreyra@estudiantes.unsam.edu.ar" },
    { id: "u3", name: "Lucía Gómez", email: "lgomez@unsam.edu.ar" },
    { id: "u4", name: "Martín Rodríguez", email: "mrodriguez@estudiantes.unsam.edu.ar" },
    { id: "u5", name: "Valentina Romero", email: "vromero@unsam-bue.edu.ar" },
    { id: "u6", name: "Joaquín Pérez", email: "jperez@estudiantes.unsam.edu.ar" },
    { id: "u7", name: "Camila Sosa", email: "csosa@unsam.edu.ar" },
    { id: "u8", name: "Tomás Núñez", email: "tnunez@estudiantes.unsam.edu.ar" },
  ];

  // The current user's works
  const myWorks = {
    borradores: [
      { id: "w_draft1", title: "Optimización de rutas de recolección urbana con algoritmos genéticos", status: "borrador", edited: "hace 2 días" },
      { id: "w_draft2", title: "Análisis de sentimiento en reseñas de productos en español", status: "procesando", edited: "hace 5 h" },
    ],
    publicados: [
      { id: "w_pub1", title: "Clasificación de imágenes satelitales con redes convolucionales", status: "publicado", date: "14 mar 2025" },
      { id: "w_pub2", title: "Estudio de microplásticos en la cuenca del Río Reconquista", status: "oculto", date: "2 feb 2025" },
    ],
  };

  // Coautores + versions + attachments for the editar workspace
  const coautores = [
    { id: "c0", name: "Sofía Maldonado", email: "smaldonado", owner: true },
    { id: "c1", name: "Carla Bianchi", email: "cbianchi", status: "aceptado" },
    { id: "c2", name: "Andrés Ferreyra", email: "aferreyra", status: "pendiente" },
    { id: "c3", name: "Lucía Gómez", email: "lgomez", status: "rechazado" },
  ];
  const versions = [
    { v: 3, file: "trabajo_v3.pdf", size: "4,2 MB", date: "14 mar 2025", current: true },
    { v: 2, file: "trabajo_v2.pdf", size: "4,0 MB", date: "2 mar 2025" },
    { v: 1, file: "trabajo_v1.pdf", size: "3,8 MB", date: "20 feb 2025" },
  ];
  const attachments = [
    { id: "a1", name: "dataset.csv", size: "880 KB" },
    { id: "a2", name: "figuras.zip", size: "12,1 MB" },
  ];

  // C12 — pending coautor invitation aimed at the current user
  const invite = {
    inviter: "Carla Bianchi",
    docId: "d_6b23e9",
    title: "Trabajo práctico: clasificación de imágenes satelitales con redes convolucionales",
  };

  // C13 — Papelera: soft-deleted works (180-day retention)
  const papelera = [
    { id: "tr_1", title: "Borrador: análisis de sentimiento en reseñas en español", deletedAt: "29 may 2026", daysLeft: 3 },
    { id: "tr_2", title: "Informe preliminar sobre calidad del aire en San Martín", deletedAt: "12 may 2026", daysLeft: 47 },
    { id: "tr_3", title: "Notas de cátedra — Estadística aplicada (2024)", deletedAt: "3 abr 2026", daysLeft: 178 },
  ];

  // C14/C15 — Moderación: report queue (docente role). Each references a doc by id.
  const reports = [
    {
      id: "rep_a1", docId: "d_5c1f88", count: 7,
      reasons: ["Plagio", "Contenido inadecuado"], last: "28 may 2026",
    },
    {
      id: "rep_b2", docId: "d_9d12af", count: 3,
      reasons: ["Error en el contenido"], last: "26 may 2026",
    },
    {
      id: "rep_c3", docId: "d_4f81c0", count: 2,
      reasons: ["Spam", "Plagio"], last: "24 may 2026",
    },
    {
      id: "rep_d4", docId: "d_7a44d2", count: 1,
      reasons: ["Spam"], last: "21 may 2026",
    },
  ];

  return { user, areas, tipos, docs, notifications, people, myWorks, coautores, versions, attachments, invite, papelera, reports };
})();
