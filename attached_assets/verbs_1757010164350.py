
#!/usr/bin/python3

"""
Lithuanian Verbs in WireWord Format for Trakaido Learning App.
Each verb follows the WireWord API interface with consolidated grammatical forms.
"""

# WireWord format verbs - each verb as a separate WireWord object
wireword_verbs = [
  {
    "guid": "V01_001",
    "base_lithuanian": "valgyti",
    "base_english": "to eat",
    "corpus": "Verbs",
    "group": "basic_needs_daily_life",
    "level": 1,
    "word_type": "verb",
    "grammatical_forms": {
      "1sg_pres": {"english": "I eat", "lithuanian": "aš valgau"},
      "2sg_pres": {"english": "you(s.) eat", "lithuanian": "tu valgai"},
      "3sg_m_pres": {"english": "he eats", "lithuanian": "jis valgo"},
      "3sg_f_pres": {"english": "she eats", "lithuanian": "ji valgo"},
      "1pl_pres": {"english": "we eat", "lithuanian": "mes valgome"},
      "2pl_pres": {"english": "you(pl.) eat", "lithuanian": "jūs valgote"},
      "3pl_m_pres": {"english": "they(m.) eat", "lithuanian": "jie valgo"},
      "3pl_f_pres": {"english": "they(f.) eat", "lithuanian": "jos valgo"},
      "1sg_past": {"english": "I ate", "lithuanian": "aš valgiau"},
      "2sg_past": {"english": "you(s.) ate", "lithuanian": "tu valgei"},
      "3sg_m_past": {"english": "he ate", "lithuanian": "jis valgė"},
      "3sg_f_past": {"english": "she ate", "lithuanian": "ji valgė"},
      "1pl_past": {"english": "we ate", "lithuanian": "mes valgėme"},
      "2pl_past": {"english": "you(pl.) ate", "lithuanian": "jūs valgėte"},
      "3pl_m_past": {"english": "they(m.) ate", "lithuanian": "jie valgė"},
      "3pl_f_past": {"english": "they(f.) ate", "lithuanian": "jos valgė"},
      "1sg_fut": {"english": "I will eat", "lithuanian": "aš valgysiu"},
      "2sg_fut": {"english": "you(s.) will eat", "lithuanian": "tu valgysi"},
      "3sg_m_fut": {"english": "he will eat", "lithuanian": "jis valgys"},
      "3sg_f_fut": {"english": "she will eat", "lithuanian": "ji valgys"},
      "1pl_fut": {"english": "we will eat", "lithuanian": "mes valgysime"},
      "2pl_fut": {"english": "you(pl.) will eat", "lithuanian": "jūs valgysite"},
      "3pl_m_fut": {"english": "they(m.) will eat", "lithuanian": "jie valgys"},
      "3pl_f_fut": {"english": "they(f.) will eat", "lithuanian": "jos valgys"}
    },
    "tags": ["basic_needs", "daily_life", "essential"]
  },

  {
    "guid": "V01_002",
    "base_lithuanian": "gyventi",
    "base_english": "to live",
    "corpus": "Verbs",
    "group": "basic_needs_daily_life",
    "level": 1,
    "word_type": "verb",
    "grammatical_forms": {
      "1sg_pres": {"english": "I live", "lithuanian": "aš gyvenu"},
      "2sg_pres": {"english": "you(s.) live", "lithuanian": "tu gyveni"},
      "3sg_m_pres": {"english": "he lives", "lithuanian": "jis gyvena"},
      "3sg_f_pres": {"english": "she lives", "lithuanian": "ji gyvena"},
      "1pl_pres": {"english": "we live", "lithuanian": "mes gyvename"},
      "2pl_pres": {"english": "you(pl.) live", "lithuanian": "jūs gyvenate"},
      "3pl_m_pres": {"english": "they(m.) live", "lithuanian": "jie gyvena"},
      "3pl_f_pres": {"english": "they(f.) live", "lithuanian": "jos gyvena"},
      "1sg_past": {"english": "I lived", "lithuanian": "aš gyvenau"},
      "2sg_past": {"english": "you(s.) lived", "lithuanian": "tu gyvenai"},
      "3sg_m_past": {"english": "he lived", "lithuanian": "jis gyveno"},
      "3sg_f_past": {"english": "she lived", "lithuanian": "ji gyveno"},
      "1pl_past": {"english": "we lived", "lithuanian": "mes gyvenome"},
      "2pl_past": {"english": "you(pl.) lived", "lithuanian": "jūs gyvenote"},
      "3pl_m_past": {"english": "they(m.) lived", "lithuanian": "jie gyveno"},
      "3pl_f_past": {"english": "they(f.) lived", "lithuanian": "jos gyveno"},
      "1sg_fut": {"english": "I will live", "lithuanian": "aš gyvensiu"},
      "2sg_fut": {"english": "you(s.) will live", "lithuanian": "tu gyvensi"},
      "3sg_m_fut": {"english": "he will live", "lithuanian": "jis gyvens"},
      "3sg_f_fut": {"english": "she will live", "lithuanian": "ji gyvens"},
      "1pl_fut": {"english": "we will live", "lithuanian": "mes gyvensime"},
      "2pl_fut": {"english": "you(pl.) will live", "lithuanian": "jūs gyvensite"},
      "3pl_m_fut": {"english": "they(m.) will live", "lithuanian": "jie gyvens"},
      "3pl_f_fut": {"english": "they(f.) will live", "lithuanian": "jos gyvens"}
    },
    "tags": ["basic_needs", "daily_life", "essential"]
  },

  {
    "guid": "V01_003",
    "base_lithuanian": "mokytis",
    "base_english": "to learn",
    "corpus": "Verbs",
    "group": "learning_knowledge",
    "level": 1,
    "word_type": "verb",
    "grammatical_forms": {
      "1sg_pres": {"english": "I learn", "lithuanian": "aš mokausi"},
      "2sg_pres": {"english": "you(s.) learn", "lithuanian": "tu mokais"},
      "3sg_m_pres": {"english": "he learns", "lithuanian": "jis mokosi"},
      "3sg_f_pres": {"english": "she learns", "lithuanian": "ji mokosi"},
      "1pl_pres": {"english": "we learn", "lithuanian": "mes mokomės"},
      "2pl_pres": {"english": "you(pl.) learn", "lithuanian": "jūs mokotės"},
      "3pl_m_pres": {"english": "they(m.) learn", "lithuanian": "jie mokosi"},
      "3pl_f_pres": {"english": "they(f.) learn", "lithuanian": "jos mokosi"},
      "1sg_past": {"english": "I learned", "lithuanian": "aš mokiausi"},
      "2sg_past": {"english": "you(s.) learned", "lithuanian": "tu mokeisi"},
      "3sg_m_past": {"english": "he learned", "lithuanian": "jis mokėsi"},
      "3sg_f_past": {"english": "she learned", "lithuanian": "ji mokėsi"},
      "1pl_past": {"english": "we learned", "lithuanian": "mes mokėmės"},
      "2pl_past": {"english": "you(pl.) learned", "lithuanian": "jūs mokėtės"},
      "3pl_m_past": {"english": "they(m.) learned", "lithuanian": "jie mokėsi"},
      "3pl_f_past": {"english": "they(f.) learned", "lithuanian": "jos mokėsi"},
      "1sg_fut": {"english": "I will learn", "lithuanian": "aš mokysiuos"},
      "2sg_fut": {"english": "you(s.) will learn", "lithuanian": "tu mokysiesi"},
      "3sg_m_fut": {"english": "he will learn", "lithuanian": "jis mokysis"},
      "3sg_f_fut": {"english": "she will learn", "lithuanian": "ji mokysis"},
      "1pl_fut": {"english": "we will learn", "lithuanian": "mes mokysimės"},
      "2pl_fut": {"english": "you(pl.) will learn", "lithuanian": "jūs mokysitės"},
      "3pl_m_fut": {"english": "they(m.) will learn", "lithuanian": "jie mokysis"},
      "3pl_f_fut": {"english": "they(f.) will learn", "lithuanian": "jos mokysis"}
    },
    "tags": ["learning", "education", "reflexive"]
  },

  {
    "guid": "V01_004",
    "base_lithuanian": "mokyti",
    "base_english": "to teach",
    "corpus": "Verbs",
    "group": "learning_knowledge",
    "level": 1,
    "word_type": "verb",
    "grammatical_forms": {
      "1sg_pres": {"english": "I teach", "lithuanian": "aš mokau"},
      "2sg_pres": {"english": "you(s.) teach", "lithuanian": "tu mokai"},
      "3sg_m_pres": {"english": "he teaches", "lithuanian": "jis moko"},
      "3sg_f_pres": {"english": "she teaches", "lithuanian": "ji moko"},
      "1pl_pres": {"english": "we teach", "lithuanian": "mes mokome"},
      "2pl_pres": {"english": "you(pl.) teach", "lithuanian": "jūs mokote"},
      "3pl_m_pres": {"english": "they(m.) teach", "lithuanian": "jie moko"},
      "3pl_f_pres": {"english": "they(f.) teach", "lithuanian": "jos moko"},
      "1sg_past": {"english": "I taught", "lithuanian": "aš mokiau"},
      "2sg_past": {"english": "you(s.) taught", "lithuanian": "tu mokei"},
      "3sg_m_past": {"english": "he taught", "lithuanian": "jis mokė"},
      "3sg_f_past": {"english": "she taught", "lithuanian": "ji mokė"},
      "1pl_past": {"english": "we taught", "lithuanian": "mes mokėme"},
      "2pl_past": {"english": "you(pl.) taught", "lithuanian": "jūs mokėte"},
      "3pl_m_past": {"english": "they(m.) taught", "lithuanian": "jie mokė"},
      "3pl_f_past": {"english": "they(f.) taught", "lithuanian": "jos mokė"},
      "1sg_fut": {"english": "I will teach", "lithuanian": "aš mokysiu"},
      "2sg_fut": {"english": "you(s.) will teach", "lithuanian": "tu mokysi"},
      "3sg_m_fut": {"english": "he will teach", "lithuanian": "jis mokys"},
      "3sg_f_fut": {"english": "she will teach", "lithuanian": "ji mokys"},
      "1pl_fut": {"english": "we will teach", "lithuanian": "mes mokysime"},
      "2pl_fut": {"english": "you(pl.) will teach", "lithuanian": "jūs mokysite"},
      "3pl_m_fut": {"english": "they(m.) will teach", "lithuanian": "jie mokys"},
      "3pl_f_fut": {"english": "they(f.) will teach", "lithuanian": "jos mokys"}
    },
    "tags": ["learning", "education", "profession"]
  },

  {
    "guid": "V01_005",
    "base_lithuanian": "žaisti",
    "base_english": "to play",
    "corpus": "Verbs",
    "group": "basic_needs_daily_life",
    "level": 1,
    "word_type": "verb",
    "grammatical_forms": {
      "1sg_pres": {"english": "I play", "lithuanian": "aš žaidžiu"},
      "2sg_pres": {"english": "you(s.) play", "lithuanian": "tu žaidi"},
      "3sg_m_pres": {"english": "he plays", "lithuanian": "jis žaidžia"},
      "3sg_f_pres": {"english": "she plays", "lithuanian": "ji žaidžia"},
      "1pl_pres": {"english": "we play", "lithuanian": "mes žaidžiame"},
      "2pl_pres": {"english": "you(pl.) play", "lithuanian": "jūs žaidžiate"},
      "3pl_m_pres": {"english": "they(m.) play", "lithuanian": "jie žaidžia"},
      "3pl_f_pres": {"english": "they(f.) play", "lithuanian": "jos žaidžia"},
      "1sg_past": {"english": "I played", "lithuanian": "aš žaidžiau"},
      "2sg_past": {"english": "you(s.) played", "lithuanian": "tu žaidei"},
      "3sg_m_past": {"english": "he played", "lithuanian": "jis žaidė"},
      "3sg_f_past": {"english": "she played", "lithuanian": "ji žaidė"},
      "1pl_past": {"english": "we played", "lithuanian": "mes žaidėme"},
      "2pl_past": {"english": "you(pl.) played", "lithuanian": "jūs žaidėte"},
      "3pl_m_past": {"english": "they(m.) played", "lithuanian": "jie žaidė"},
      "3pl_f_past": {"english": "they(f.) played", "lithuanian": "jos žaidė"},
      "1sg_fut": {"english": "I will play", "lithuanian": "aš žaisiu"},
      "2sg_fut": {"english": "you(s.) will play", "lithuanian": "tu žaisi"},
      "3sg_m_fut": {"english": "he will play", "lithuanian": "jis žais"},
      "3sg_f_fut": {"english": "she will play", "lithuanian": "ji žais"},
      "1pl_fut": {"english": "we will play", "lithuanian": "mes žaisime"},
      "2pl_fut": {"english": "you(pl.) will play", "lithuanian": "jūs žaisite"},
      "3pl_m_fut": {"english": "they(m.) will play", "lithuanian": "jie žais"},
      "3pl_f_fut": {"english": "they(f.) will play", "lithuanian": "jos žais"}
    },
    "tags": ["recreation", "daily_life", "entertainment"]
  },

  {
    "guid": "V01_006",
    "base_lithuanian": "skaityti",
    "base_english": "to read",
    "corpus": "Verbs",
    "group": "learning_knowledge",
    "level": 1,
    "word_type": "verb",
    "grammatical_forms": {
      "1sg_pres": {"english": "I read (pres. tense)", "lithuanian": "aš skaitau"},
      "2sg_pres": {"english": "you(s.) read (pres. tense)", "lithuanian": "tu skaitai"},
      "3sg_m_pres": {"english": "he reads", "lithuanian": "jis skaito"},
      "3sg_f_pres": {"english": "she reads", "lithuanian": "ji skaito"},
      "1pl_pres": {"english": "we read (pres. tense)", "lithuanian": "mes skaitome"},
      "2pl_pres": {"english": "you(pl.) read (pres. tense)", "lithuanian": "jūs skaitote"},
      "3pl_m_pres": {"english": "they(m.) read (pres. tense)", "lithuanian": "jie skaito"},
      "3pl_f_pres": {"english": "they(f.) read (pres. tense)", "lithuanian": "jos skaito"},
      "1sg_past": {"english": "I read (past tense)", "lithuanian": "aš skaičiau"},
      "2sg_past": {"english": "you(s.) read (past tense)", "lithuanian": "tu skaitei"},
      "3sg_m_past": {"english": "he read (past tense)", "lithuanian": "jis skaitė"},
      "3sg_f_past": {"english": "she read (past tense)", "lithuanian": "ji skaitė"},
      "1pl_past": {"english": "we read (past tense)", "lithuanian": "mes skaitėme"},
      "2pl_past": {"english": "you(pl.) read (past tense)", "lithuanian": "jūs skaitėte"},
      "3pl_m_past": {"english": "they(m.) read (past tense)", "lithuanian": "jie skaitė"},
      "3pl_f_past": {"english": "they(f.) read (past tense)", "lithuanian": "jos skaitė"},
      "1sg_fut": {"english": "I will read", "lithuanian": "aš skaitysiu"},
      "2sg_fut": {"english": "you(s.) will read", "lithuanian": "tu skaitysi"},
      "3sg_m_fut": {"english": "he will read", "lithuanian": "jis skaitys"},
      "3sg_f_fut": {"english": "she will read", "lithuanian": "ji skaitys"},
      "1pl_fut": {"english": "we will read", "lithuanian": "mes skaitysime"},
      "2pl_fut": {"english": "you(pl.) will read", "lithuanian": "jūs skaitysite"},
      "3pl_m_fut": {"english": "they(m.) will read", "lithuanian": "jie skaitys"},
      "3pl_f_fut": {"english": "they(f.) will read", "lithuanian": "jos skaitys"}
    },
    "tags": ["learning", "literacy", "education"]
  },

  {
    "guid": "V01_007",
    "base_lithuanian": "rašyti",
    "base_english": "to write",
    "corpus": "Verbs",
    "group": "learning_knowledge",
    "level": 1,
    "word_type": "verb",
    "grammatical_forms": {
      "1sg_pres": {"english": "I write", "lithuanian": "aš rašau"},
      "2sg_pres": {"english": "you(s.) write", "lithuanian": "tu rašai"},
      "3sg_m_pres": {"english": "he writes", "lithuanian": "jis rašo"},
      "3sg_f_pres": {"english": "she writes", "lithuanian": "ji rašo"},
      "1pl_pres": {"english": "we write", "lithuanian": "mes rašome"},
      "2pl_pres": {"english": "you(pl.) write", "lithuanian": "jūs rašote"},
      "3pl_m_pres": {"english": "they(m.) write", "lithuanian": "jie rašo"},
      "3pl_f_pres": {"english": "they(f.) write", "lithuanian": "jos rašo"},
      "1sg_past": {"english": "I wrote", "lithuanian": "aš rašiau"},
      "2sg_past": {"english": "you(s.) wrote", "lithuanian": "tu rašei"},
      "3sg_m_past": {"english": "he wrote", "lithuanian": "jis rašė"},
      "3sg_f_past": {"english": "she wrote", "lithuanian": "ji rašė"},
      "1pl_past": {"english": "we wrote", "lithuanian": "mes rašėme"},
      "2pl_past": {"english": "you(pl.) wrote", "lithuanian": "jūs rašėte"},
      "3pl_m_past": {"english": "they(m.) wrote", "lithuanian": "jie rašė"},
      "3pl_f_past": {"english": "they(f.) wrote", "lithuanian": "jos rašė"},
      "1sg_fut": {"english": "I will write", "lithuanian": "aš rašysiu"},
      "2sg_fut": {"english": "you(s.) will write", "lithuanian": "tu rašysi"},
      "3sg_m_fut": {"english": "he will write", "lithuanian": "jis rašys"},
      "3sg_f_fut": {"english": "she will write", "lithuanian": "ji rašys"},
      "1pl_fut": {"english": "we will write", "lithuanian": "mes rašysime"},
      "2pl_fut": {"english": "you(pl.) will write", "lithuanian": "jūs rašysite"},
      "3pl_m_fut": {"english": "they(m.) will write", "lithuanian": "jie rašys"},
      "3pl_f_fut": {"english": "they(f.) will write", "lithuanian": "jos rašys"}
    },
    "tags": ["learning", "literacy", "education"]
  },

  {
    "guid": "V01_008",
    "base_lithuanian": "klausyti",
    "base_english": "to listen",
    "corpus": "Verbs",
    "group": "sensory_perception",
    "level": 1,
    "word_type": "verb",
    "grammatical_forms": {
      "1sg_pres": {"english": "I listen", "lithuanian": "aš klausau"},
      "2sg_pres": {"english": "you(s.) listen", "lithuanian": "tu klausai"},
      "3sg_m_pres": {"english": "he listens", "lithuanian": "jis klauso"},
      "3sg_f_pres": {"english": "she listens", "lithuanian": "ji klauso"},
      "1pl_pres": {"english": "we listen", "lithuanian": "mes klausome"},
      "2pl_pres": {"english": "you(pl.) listen", "lithuanian": "jūs klausote"},
      "3pl_m_pres": {"english": "they(m.) listen", "lithuanian": "jie klauso"},
      "3pl_f_pres": {"english": "they(f.) listen", "lithuanian": "jos klauso"},
      "1sg_past": {"english": "I listened", "lithuanian": "aš klausiau"},
      "2sg_past": {"english": "you(s.) listened", "lithuanian": "tu klausei"},
      "3sg_m_past": {"english": "he listened", "lithuanian": "jis klausė"},
      "3sg_f_past": {"english": "she listened", "lithuanian": "ji klausė"},
      "1pl_past": {"english": "we listened", "lithuanian": "mes klausėme"},
      "2pl_past": {"english": "you(pl.) listened", "lithuanian": "jūs klausėte"},
      "3pl_m_past": {"english": "they(m.) listened", "lithuanian": "jie klausė"},
      "3pl_f_past": {"english": "they(f.) listened", "lithuanian": "jos klausė"},
      "1sg_fut": {"english": "I will listen", "lithuanian": "aš klausysiu"},
      "2sg_fut": {"english": "you(s.) will listen", "lithuanian": "tu klausysi"},
      "3sg_m_fut": {"english": "he will listen", "lithuanian": "jis klausys"},
      "3sg_f_fut": {"english": "she will listen", "lithuanian": "ji klausys"},
      "1pl_fut": {"english": "we will listen", "lithuanian": "mes klausysime"},
      "2pl_fut": {"english": "you(pl.) will listen", "lithuanian": "jūs klausysite"},
      "3pl_m_fut": {"english": "they(m.) will listen", "lithuanian": "jie klausys"},
      "3pl_f_fut": {"english": "they(f.) will listen", "lithuanian": "jos klausys"}
    },
    "tags": ["perception", "communication", "senses"]
  },

  {
    "guid": "V01_009",
    "base_lithuanian": "dirbti",
    "base_english": "to work",
    "corpus": "Verbs",
    "group": "basic_needs_daily_life",
    "level": 1,
    "word_type": "verb",
    "grammatical_forms": {
      "1sg_pres": {"english": "I work", "lithuanian": "aš dirbu"},
      "2sg_pres": {"english": "you(s.) work", "lithuanian": "tu dirbi"},
      "3sg_m_pres": {"english": "he works", "lithuanian": "jis dirba"},
      "3sg_f_pres": {"english": "she works", "lithuanian": "ji dirba"},
      "1pl_pres": {"english": "we work", "lithuanian": "mes dirbame"},
      "2pl_pres": {"english": "you(pl.) work", "lithuanian": "jūs dirbate"},
      "3pl_m_pres": {"english": "they(m.) work", "lithuanian": "jie dirba"},
      "3pl_f_pres": {"english": "they(f.) work", "lithuanian": "jos dirba"},
      "1sg_past": {"english": "I worked", "lithuanian": "aš dirbau"},
      "2sg_past": {"english": "you(s.) worked", "lithuanian": "tu dirbai"},
      "3sg_m_past": {"english": "he worked", "lithuanian": "jis dirbo"},
      "3sg_f_past": {"english": "she worked", "lithuanian": "ji dirbo"},
      "1pl_past": {"english": "we worked", "lithuanian": "mes dirbome"},
      "2pl_past": {"english": "you(pl.) worked", "lithuanian": "jūs dirbote"},
      "3pl_m_past": {"english": "they(m.) worked", "lithuanian": "jie dirbo"},
      "3pl_f_past": {"english": "they(f.) worked", "lithuanian": "jos dirbo"},
      "1sg_fut": {"english": "I will work", "lithuanian": "aš dirbsiu"},
      "2sg_fut": {"english": "you(s.) will work", "lithuanian": "tu dirbsi"},
      "3sg_m_fut": {"english": "he will work", "lithuanian": "jis dirbs"},
      "3sg_f_fut": {"english": "she will work", "lithuanian": "ji dirbs"},
      "1pl_fut": {"english": "we will work", "lithuanian": "mes dirbsime"},
      "2pl_fut": {"english": "you(pl.) will work", "lithuanian": "jūs dirbsite"},
      "3pl_m_fut": {"english": "they(m.) will work", "lithuanian": "jie dirbs"},
      "3pl_f_fut": {"english": "they(f.) will work", "lithuanian": "jos dirbs"}
    },
    "tags": ["profession", "daily_life", "essential"]
  },

  {
    "guid": "V01_010",
    "base_lithuanian": "gerti",
    "base_english": "to drink",
    "corpus": "Verbs",
    "group": "basic_needs_daily_life",
    "level": 1,
    "word_type": "verb",
    "grammatical_forms": {
      "1sg_pres": {"english": "I drink", "lithuanian": "aš geriu"},
      "2sg_pres": {"english": "you(s.) drink", "lithuanian": "tu geri"},
      "3sg_m_pres": {"english": "he drinks", "lithuanian": "jis geria"},
      "3sg_f_pres": {"english": "she drinks", "lithuanian": "ji geria"},
      "1pl_pres": {"english": "we drink", "lithuanian": "mes geriame"},
      "2pl_pres": {"english": "you(pl.) drink", "lithuanian": "jūs geriate"},
      "3pl_m_pres": {"english": "they(m.) drink", "lithuanian": "jie geria"},
      "3pl_f_pres": {"english": "they(f.) drink", "lithuanian": "jos geria"},
      "1sg_past": {"english": "I drank", "lithuanian": "aš gėriau"},
      "2sg_past": {"english": "you(s.) drank", "lithuanian": "tu gėrei"},
      "3sg_m_past": {"english": "he drank", "lithuanian": "jis gėrė"},
      "3sg_f_past": {"english": "she drank", "lithuanian": "ji gėrė"},
      "1pl_past": {"english": "we drank", "lithuanian": "mes gėrėme"},
      "2pl_past": {"english": "you(pl.) drank", "lithuanian": "jūs gėrėte"},
      "3pl_m_past": {"english": "they(m.) drank", "lithuanian": "jie gėrė"},
      "3pl_f_past": {"english": "they(f.) drank", "lithuanian": "jos gėrė"},
      "1sg_fut": {"english": "I will drink", "lithuanian": "aš gersiu"},
      "2sg_fut": {"english": "you(s.) will drink", "lithuanian": "tu gersi"},
      "3sg_m_fut": {"english": "he will drink", "lithuanian": "jis gers"},
      "3sg_f_fut": {"english": "she will drink", "lithuanian": "ji gers"},
      "1pl_fut": {"english": "we will drink", "lithuanian": "mes gersime"},
      "2pl_fut": {"english": "you(pl.) will drink", "lithuanian": "jūs gersite"},
      "3pl_m_fut": {"english": "they(m.) will drink", "lithuanian": "jie gers"},
      "3pl_f_fut": {"english": "they(f.) will drink", "lithuanian": "jos gers"}
    },
    "tags": ["basic_needs", "daily_life", "essential"]
  },

  {
    "guid": "V01_011",
    "base_lithuanian": "miegoti",
    "base_english": "to sleep",
    "corpus": "Verbs",
    "group": "basic_needs_daily_life",
    "level": 1,
    "word_type": "verb",
    "grammatical_forms": {
      "1sg_pres": {"english": "I sleep", "lithuanian": "aš miegu"},
      "2sg_pres": {"english": "you(s.) sleep", "lithuanian": "tu miegi"},
      "3sg_m_pres": {"english": "he sleeps", "lithuanian": "jis miega"},
      "3sg_f_pres": {"english": "she sleeps", "lithuanian": "ji miega"},
      "1pl_pres": {"english": "we sleep", "lithuanian": "mes miegame"},
      "2pl_pres": {"english": "you(pl.) sleep", "lithuanian": "jūs miegate"},
      "3pl_m_pres": {"english": "they(m.) sleep", "lithuanian": "jie miega"},
      "3pl_f_pres": {"english": "they(f.) sleep", "lithuanian": "jos miega"},
      "1sg_past": {"english": "I slept", "lithuanian": "aš miegojau"},
      "2sg_past": {"english": "you(s.) slept", "lithuanian": "tu miegojai"},
      "3sg_m_past": {"english": "he slept", "lithuanian": "jis miegojo"},
      "3sg_f_past": {"english": "she slept", "lithuanian": "ji miegojo"},
      "1pl_past": {"english": "we slept", "lithuanian": "mes miegojome"},
      "2pl_past": {"english": "you(pl.) slept", "lithuanian": "jūs miegojote"},
      "3pl_m_past": {"english": "they(m.) slept", "lithuanian": "jie miegojo"},
      "3pl_f_past": {"english": "they(f.) slept", "lithuanian": "jos miegojo"},
      "1sg_fut": {"english": "I will sleep", "lithuanian": "aš miegosiu"},
      "2sg_fut": {"english": "you(s.) will sleep", "lithuanian": "tu miegosi"},
      "3sg_m_fut": {"english": "he will sleep", "lithuanian": "jis miegos"},
      "3sg_f_fut": {"english": "she will sleep", "lithuanian": "ji miegos"},
      "1pl_fut": {"english": "we will sleep", "lithuanian": "mes miegosime"},
      "2pl_fut": {"english": "you(pl.) will sleep", "lithuanian": "jūs miegosite"},
      "3pl_m_fut": {"english": "they(m.) will sleep", "lithuanian": "jie miegos"},
      "3pl_f_fut": {"english": "they(f.) will sleep", "lithuanian": "jos miegos"}
    },
    "tags": ["basic_needs", "daily_life", "essential"]
  },

  {
    "guid": "V01_012",
    "base_lithuanian": "būti",
    "base_english": "to be",
    "corpus": "Verbs",
    "group": "actions_transactions",
    "level": 1,
    "word_type": "verb",
    "grammatical_forms": {
      "1sg_pres": {"english": "I am", "lithuanian": "aš esu"},
      "2sg_pres": {"english": "you(s.) are", "lithuanian": "tu esi"},
      "3sg_m_pres": {"english": "he is", "lithuanian": "jis yra"},
      "3sg_f_pres": {"english": "she is", "lithuanian": "ji yra"},
      "1pl_pres": {"english": "we are", "lithuanian": "mes esame"},
      "2pl_pres": {"english": "you(pl.) are", "lithuanian": "jūs esate"},
      "3pl_m_pres": {"english": "they(m.) are", "lithuanian": "jie yra"},
      "3pl_f_pres": {"english": "they(f.) are", "lithuanian": "jos yra"},
      "1sg_past": {"english": "I was", "lithuanian": "aš buvau"},
      "2sg_past": {"english": "you(s.) were", "lithuanian": "tu buvai"},
      "3sg_m_past": {"english": "he was", "lithuanian": "jis buvo"},
      "3sg_f_past": {"english": "she was", "lithuanian": "ji buvo"},
      "1pl_past": {"english": "we were", "lithuanian": "mes buvome"},
      "2pl_past": {"english": "you(pl.) were", "lithuanian": "jūs buvote"},
      "3pl_m_past": {"english": "they(m.) were", "lithuanian": "jie buvo"},
      "3pl_f_past": {"english": "they(f.) were", "lithuanian": "jos buvo"},
      "1sg_fut": {"english": "I will be", "lithuanian": "aš būsiu"},
      "2sg_fut": {"english": "you(s.) will be", "lithuanian": "tu būsi"},
      "3sg_m_fut": {"english": "he will be", "lithuanian": "jis bus"},
      "3sg_f_fut": {"english": "she will be", "lithuanian": "ji bus"},
      "1pl_fut": {"english": "we will be", "lithuanian": "mes būsime"},
      "2pl_fut": {"english": "you(pl.) will be", "lithuanian": "jūs būsite"},
      "3pl_m_fut": {"english": "they(m.) will be", "lithuanian": "jie bus"},
      "3pl_f_fut": {"english": "they(f.) will be", "lithuanian": "jos bus"}
    },
    "tags": ["essential", "copula", "irregular"]
  },

  {
    "guid": "V01_013",
    "base_lithuanian": "turėti",
    "base_english": "to have",
    "corpus": "Verbs",
    "group": "actions_transactions",
    "level": 1,
    "word_type": "verb",
    "grammatical_forms": {
      "1sg_pres": {"english": "I have", "lithuanian": "aš turiu"},
      "2sg_pres": {"english": "you(s.) have", "lithuanian": "tu turi"},
      "3sg_m_pres": {"english": "he has", "lithuanian": "jis turi"},
      "3sg_f_pres": {"english": "she has", "lithuanian": "ji turi"},
      "1pl_pres": {"english": "we have", "lithuanian": "mes turime"},
      "2pl_pres": {"english": "you(pl.) have", "lithuanian": "jūs turite"},
      "3pl_m_pres": {"english": "they(m.) have", "lithuanian": "jie turi"},
      "3pl_f_pres": {"english": "they(f.) have", "lithuanian": "jos turi"},
      "1sg_past": {"english": "I had", "lithuanian": "aš turėjau"},
      "2sg_past": {"english": "you(s.) had", "lithuanian": "tu turėjai"},
      "3sg_m_past": {"english": "he had", "lithuanian": "jis turėjo"},
      "3sg_f_past": {"english": "she had", "lithuanian": "ji turėjo"},
      "1pl_past": {"english": "we had", "lithuanian": "mes turėjome"},
      "2pl_past": {"english": "you(pl.) had", "lithuanian": "jūs turėjote"},
      "3pl_m_past": {"english": "they(m.) had", "lithuanian": "jie turėjo"},
      "3pl_f_past": {"english": "they(f.) had", "lithuanian": "jos turėjo"},
      "1sg_fut": {"english": "I will have", "lithuanian": "aš turėsiu"},
      "2sg_fut": {"english": "you(s.) will have", "lithuanian": "tu turėsi"},
      "3sg_m_fut": {"english": "he will have", "lithuanian": "jis turės"},
      "3sg_f_fut": {"english": "she will have", "lithuanian": "ji turės"},
      "1pl_fut": {"english": "we will have", "lithuanian": "mes turėsime"},
      "2pl_fut": {"english": "you(pl.) will have", "lithuanian": "jūs turėsite"},
      "3pl_m_fut": {"english": "they(m.) will have", "lithuanian": "jie turės"},
      "3pl_f_fut": {"english": "they(f.) will have", "lithuanian": "jos turės"}
    },
    "tags": ["essential", "possession", "auxiliary"]
  },

  {
    "guid": "V01_014",
    "base_lithuanian": "mėgti",
    "base_english": "to like",
    "corpus": "Verbs",
    "group": "mental_emotional",
    "level": 1,
    "word_type": "verb",
    "grammatical_forms": {
      "1sg_pres": {"english": "I like", "lithuanian": "aš mėgstu"},
      "2sg_pres": {"english": "you(s.) like", "lithuanian": "tu mėgsti"},
      "3sg_m_pres": {"english": "he likes", "lithuanian": "jis mėgsta"},
      "3sg_f_pres": {"english": "she likes", "lithuanian": "ji mėgsta"},
      "1pl_pres": {"english": "we like", "lithuanian": "mes mėgstame"},
      "2pl_pres": {"english": "you(pl.) like", "lithuanian": "jūs mėgstate"},
      "3pl_m_pres": {"english": "they(m.) like", "lithuanian": "jie mėgsta"},
      "3pl_f_pres": {"english": "they(f.) like", "lithuanian": "jos mėgsta"},
      "1sg_past": {"english": "I liked", "lithuanian": "aš mėgau"},
      "2sg_past": {"english": "you(s.) liked", "lithuanian": "tu mėgai"},
      "3sg_m_past": {"english": "he liked", "lithuanian": "jis mėgo"},
      "3sg_f_past": {"english": "she liked", "lithuanian": "ji mėgo"},
      "1pl_past": {"english": "we liked", "lithuanian": "mes mėgome"},
      "2pl_past": {"english": "you(pl.) liked", "lithuanian": "jūs mėgote"},
      "3pl_m_past": {"english": "they(m.) liked", "lithuanian": "jie mėgo"},
      "3pl_f_past": {"english": "they(f.) liked", "lithuanian": "jos mėgo"},
      "1sg_fut": {"english": "I will like", "lithuanian": "aš mėgsiu"},
      "2sg_fut": {"english": "you(s.) will like", "lithuanian": "tu mėgsi"},
      "3sg_m_fut": {"english": "he will like", "lithuanian": "jis mėgs"},
      "3sg_f_fut": {"english": "she will like", "lithuanian": "ji mėgs"},
      "1pl_fut": {"english": "we will like", "lithuanian": "mes mėgsime"},
      "2pl_fut": {"english": "you(pl.) will like", "lithuanian": "jūs mėgsite"},
      "3pl_m_fut": {"english": "they(m.) will like", "lithuanian": "jie mėgs"},
      "3pl_f_fut": {"english": "they(f.) will like", "lithuanian": "jos mėgs"}
    },
    "tags": ["emotion", "preference", "essential"]
  },

  {
    "guid": "V01_015",
    "base_lithuanian": "gaminti",
    "base_english": "to make",
    "corpus": "Verbs",
    "group": "actions_transactions",
    "level": 1,
    "word_type": "verb",
    "grammatical_forms": {
      "1sg_pres": {"english": "I make", "lithuanian": "aš gaminu"},
      "2sg_pres": {"english": "you(s.) make", "lithuanian": "tu gamini"},
      "3sg_m_pres": {"english": "he makes", "lithuanian": "jis gamina"},
      "3sg_f_pres": {"english": "she makes", "lithuanian": "ji gamina"},
      "1pl_pres": {"english": "we make", "lithuanian": "mes gaminame"},
      "2pl_pres": {"english": "you(pl.) make", "lithuanian": "jūs gaminate"},
      "3pl_m_pres": {"english": "they(m.) make", "lithuanian": "jie gamina"},
      "3pl_f_pres": {"english": "they(f.) make", "lithuanian": "jos gamina"},
      "1sg_past": {"english": "I made", "lithuanian": "aš gaminau"},
      "2sg_past": {"english": "you(s.) made", "lithuanian": "tu gaminai"},
      "3sg_m_past": {"english": "he made", "lithuanian": "jis gamino"},
      "3sg_f_past": {"english": "she made", "lithuanian": "ji gamino"},
      "1pl_past": {"english": "we made", "lithuanian": "mes gaminome"},
      "2pl_past": {"english": "you(pl.) made", "lithuanian": "jūs gaminote"},
      "3pl_m_past": {"english": "they(m.) made", "lithuanian": "jie gamino"},
      "3pl_f_past": {"english": "they(f.) made", "lithuanian": "jos gamino"},
      "1sg_fut": {"english": "I will make", "lithuanian": "aš gaminsiu"},
      "2sg_fut": {"english": "you(s.) will make", "lithuanian": "tu gaminsi"},
      "3sg_m_fut": {"english": "he will make", "lithuanian": "jis gamins"},
      "3sg_f_fut": {"english": "she will make", "lithuanian": "ji gamins"},
      "1pl_fut": {"english": "we will make", "lithuanian": "mes gaminsime"},
      "2pl_fut": {"english": "you(pl.) will make", "lithuanian": "jūs gaminsite"},
      "3pl_m_fut": {"english": "they(m.) will make", "lithuanian": "jie gamins"},
      "3pl_f_fut": {"english": "they(f.) will make", "lithuanian": "jos gamins"}
    },
    "tags": ["creation", "production", "action"]
  },

  {
    "guid": "V01_016",
    "base_lithuanian": "pirkti",
    "base_english": "to buy",
    "corpus": "Verbs",
    "group": "actions_transactions",
    "level": 1,
    "word_type": "verb",
    "grammatical_forms": {
      "1sg_pres": {"english": "I buy", "lithuanian": "aš perku"},
      "2sg_pres": {"english": "you(s.) buy", "lithuanian": "tu perki"},
      "3sg_m_pres": {"english": "he buys", "lithuanian": "jis perka"},
      "3sg_f_pres": {"english": "she buys", "lithuanian": "ji perka"},
      "1pl_pres": {"english": "we buy", "lithuanian": "mes perkame"},
      "2pl_pres": {"english": "you(pl.) buy", "lithuanian": "jūs perkate"},
      "3pl_m_pres": {"english": "they(m.) buy", "lithuanian": "jie perka"},
      "3pl_f_pres": {"english": "they(f.) buy", "lithuanian": "jos perka"},
      "1sg_past": {"english": "I bought", "lithuanian": "aš pirkau"},
      "2sg_past": {"english": "you(s.) bought", "lithuanian": "tu pirkai"},
      "3sg_m_past": {"english": "he bought", "lithuanian": "jis pirko"},
      "3sg_f_past": {"english": "she bought", "lithuanian": "ji pirko"},
      "1pl_past": {"english": "we bought", "lithuanian": "mes pirkome"},
      "2pl_past": {"english": "you(pl.) bought", "lithuanian": "jūs pirkote"},
      "3pl_m_past": {"english": "they(m.) bought", "lithuanian": "jie pirko"},
      "3pl_f_past": {"english": "they(f.) bought", "lithuanian": "jos pirko"},
      "1sg_fut": {"english": "I will buy", "lithuanian": "aš pirksiu"},
      "2sg_fut": {"english": "you(s.) will buy", "lithuanian": "tu pirksi"},
      "3sg_m_fut": {"english": "he will buy", "lithuanian": "jis pirks"},
      "3sg_f_fut": {"english": "she will buy", "lithuanian": "ji pirks"},
      "1pl_fut": {"english": "we will buy", "lithuanian": "mes pirksime"},
      "2pl_fut": {"english": "you(pl.) will buy", "lithuanian": "jūs pirksite"},
      "3pl_m_fut": {"english": "they(m.) will buy", "lithuanian": "jie pirks"},
      "3pl_f_fut": {"english": "they(f.) will buy", "lithuanian": "jos pirks"}
    },
    "tags": ["transaction", "commerce", "daily_life"]
  },

  {
    "guid": "V01_017",
    "base_lithuanian": "duoti",
    "base_english": "to give",
    "corpus": "Verbs",
    "group": "actions_transactions",
    "level": 1,
    "word_type": "verb",
    "grammatical_forms": {
      "1sg_pres": {"english": "I give", "lithuanian": "aš duodu"},
      "2sg_pres": {"english": "you(s.) give", "lithuanian": "tu duodi"},
      "3sg_m_pres": {"english": "he gives", "lithuanian": "jis duoda"},
      "3sg_f_pres": {"english": "she gives", "lithuanian": "ji duoda"},
      "1pl_pres": {"english": "we give", "lithuanian": "mes duodame"},
      "2pl_pres": {"english": "you(pl.) give", "lithuanian": "jūs duodate"},
      "3pl_m_pres": {"english": "they(m.) give", "lithuanian": "jie duoda"},
      "3pl_f_pres": {"english": "they(f.) give", "lithuanian": "jos duoda"},
      "1sg_past": {"english": "I gave", "lithuanian": "aš daviau"},
      "2sg_past": {"english": "you(s.) gave", "lithuanian": "tu davei"},
      "3sg_m_past": {"english": "he gave", "lithuanian": "jis davė"},
      "3sg_f_past": {"english": "she gave", "lithuanian": "ji davė"},
      "1pl_past": {"english": "we gave", "lithuanian": "mes davėme"},
      "2pl_past": {"english": "you(pl.) gave", "lithuanian": "jūs davėte"},
      "3pl_m_past": {"english": "they(m.) gave", "lithuanian": "jie davė"},
      "3pl_f_past": {"english": "they(f.) gave", "lithuanian": "jos davė"},
      "1sg_fut": {"english": "I will give", "lithuanian": "aš duosiu"},
      "2sg_fut": {"english": "you(s.) will give", "lithuanian": "tu duosi"},
      "3sg_m_fut": {"english": "he will give", "lithuanian": "jis duos"},
      "3sg_f_fut": {"english": "she will give", "lithuanian": "ji duos"},
      "1pl_fut": {"english": "we will give", "lithuanian": "mes duosime"},
      "2pl_fut": {"english": "you(pl.) will give", "lithuanian": "jūs duosite"},
      "3pl_m_fut": {"english": "they(m.) will give", "lithuanian": "jie duos"},
      "3pl_f_fut": {"english": "they(f.) will give", "lithuanian": "jos duos"}
    },
    "tags": ["transaction", "generosity", "action"]
  },

  {
    "guid": "V01_018",
    "base_lithuanian": "imti",
    "base_english": "to take",
    "corpus": "Verbs",
    "group": "actions_transactions",
    "level": 1,
    "word_type": "verb",
    "grammatical_forms": {
      "1sg_pres": {"english": "I take", "lithuanian": "aš imu"},
      "2sg_pres": {"english": "you(s.) take", "lithuanian": "tu imi"},
      "3sg_m_pres": {"english": "he takes", "lithuanian": "jis ima"},
      "3sg_f_pres": {"english": "she takes", "lithuanian": "ji ima"},
      "1pl_pres": {"english": "we take", "lithuanian": "mes imame"},
      "2pl_pres": {"english": "you(pl.) take", "lithuanian": "jūs imate"},
      "3pl_m_pres": {"english": "they(m.) take", "lithuanian": "jie ima"},
      "3pl_f_pres": {"english": "they(f.) take", "lithuanian": "jos ima"},
      "1sg_past": {"english": "I took", "lithuanian": "aš ėmiau"},
      "2sg_past": {"english": "you(s.) took", "lithuanian": "tu ėmei"},
      "3sg_m_past": {"english": "he took", "lithuanian": "jis ėmė"},
      "3sg_f_past": {"english": "she took", "lithuanian": "ji ėmė"},
      "1pl_past": {"english": "we took", "lithuanian": "mes ėmėme"},
      "2pl_past": {"english": "you(pl.) took", "lithuanian": "jūs ėmėte"},
      "3pl_m_past": {"english": "they(m.) took", "lithuanian": "jie ėmė"},
      "3pl_f_past": {"english": "they(f.) took", "lithuanian": "jos ėmė"},
      "1sg_fut": {"english": "I will take", "lithuanian": "aš imsiu"},
      "2sg_fut": {"english": "you(s.) will take", "lithuanian": "tu imsi"},
      "3sg_m_fut": {"english": "he will take", "lithuanian": "jis ims"},
      "3sg_f_fut": {"english": "she will take", "lithuanian": "ji ims"},
      "1pl_fut": {"english": "we will take", "lithuanian": "mes imsime"},
      "2pl_fut": {"english": "you(pl.) will take", "lithuanian": "jūs imsite"},
      "3pl_m_fut": {"english": "they(m.) will take", "lithuanian": "jie ims"},
      "3pl_f_fut": {"english": "they(f.) will take", "lithuanian": "jos ims"}
    },
    "tags": ["action", "acquisition", "essential"]
  },

  {
    "guid": "V01_019",
    "base_lithuanian": "eiti",
    "base_english": "to walk",
    "corpus": "Verbs",
    "group": "movement_travel",
    "level": 1,
    "word_type": "verb",
    "grammatical_forms": {
      "1sg_pres": {"english": "I walk", "lithuanian": "aš einu"},
      "2sg_pres": {"english": "you(s.) walk", "lithuanian": "tu eini"},
      "3sg_m_pres": {"english": "he walks", "lithuanian": "jis eina"},
      "3sg_f_pres": {"english": "she walks", "lithuanian": "ji eina"},
      "1pl_pres": {"english": "we walk", "lithuanian": "mes einame"},
      "2pl_pres": {"english": "you(pl.) walk", "lithuanian": "jūs einate"},
      "3pl_m_pres": {"english": "they(m.) walk", "lithuanian": "jie eina"},
      "3pl_f_pres": {"english": "they(f.) walk", "lithuanian": "jos eina"},
      "1sg_past": {"english": "I walked", "lithuanian": "aš ėjau"},
      "2sg_past": {"english": "you(s.) walked", "lithuanian": "tu ėjai"},
      "3sg_m_past": {"english": "he walked", "lithuanian": "jis ėjo"},
      "3sg_f_past": {"english": "she walked", "lithuanian": "ji ėjo"},
      "1pl_past": {"english": "we walked", "lithuanian": "mes ėjome"},
      "2pl_past": {"english": "you(pl.) walked", "lithuanian": "jūs ėjote"},
      "3pl_m_past": {"english": "they(m.) walked", "lithuanian": "jie ėjo"},
      "3pl_f_past": {"english": "they(f.) walked", "lithuanian": "jos ėjo"},
      "1sg_fut": {"english": "I will walk", "lithuanian": "aš eisiu"},
      "2sg_fut": {"english": "you(s.) will walk", "lithuanian": "tu eisi"},
      "3sg_m_fut": {"english": "he will walk", "lithuanian": "jis eis"},
      "3sg_f_fut": {"english": "she will walk", "lithuanian": "ji eis"},
      "1pl_fut": {"english": "we will walk", "lithuanian": "mes eisime"},
      "2pl_fut": {"english": "you(pl.) will walk", "lithuanian": "jūs eisite"},
      "3pl_m_fut": {"english": "they(m.) will walk", "lithuanian": "jie eis"},
      "3pl_f_fut": {"english": "they(f.) will walk", "lithuanian": "jos eis"}
    },
    "english_alternatives": ["go"],
    "tags": ["movement", "travel", "basic_action"]
  },

  {
    "guid": "V01_020",
    "base_lithuanian": "važiuoti",
    "base_english": "to drive",
    "corpus": "Verbs",
    "group": "movement_travel",
    "level": 1,
    "word_type": "verb",
    "grammatical_forms": {
      "1sg_pres": {"english": "I drive", "lithuanian": "aš važiuoju"},
      "2sg_pres": {"english": "you(s.) drive", "lithuanian": "tu važiuoji"},
      "3sg_m_pres": {"english": "he drives", "lithuanian": "jis važiuoja"},
      "3sg_f_pres": {"english": "she drives", "lithuanian": "ji važiuoja"},
      "1pl_pres": {"english": "we drive", "lithuanian": "mes važiuojame"},
      "2pl_pres": {"english": "you(pl.) drive", "lithuanian": "jūs važiuojate"},
      "3pl_m_pres": {"english": "they(m.) drive", "lithuanian": "jie važiuoja"},
      "3pl_f_pres": {"english": "they(f.) drive", "lithuanian": "jos važiuoja"},
      "1sg_past": {"english": "I drove", "lithuanian": "aš važiavau"},
      "2sg_past": {"english": "you(s.) drove", "lithuanian": "tu važiavai"},
      "3sg_m_past": {"english": "he drove", "lithuanian": "jis važiavo"},
      "3sg_f_past": {"english": "she drove", "lithuanian": "ji važiavo"},
      "1pl_past": {"english": "we drove", "lithuanian": "mes važiavome"},
      "2pl_past": {"english": "you(pl.) drove", "lithuanian": "jūs važiavote"},
      "3pl_m_past": {"english": "they(m.) drove", "lithuanian": "jie važiavo"},
      "3pl_f_past": {"english": "they(f.) drove", "lithuanian": "jos važiavo"},
      "1sg_fut": {"english": "I will drive", "lithuanian": "aš važiuosiu"},
      "2sg_fut": {"english": "you(s.) will drive", "lithuanian": "tu važiuosi"},
      "3sg_m_fut": {"english": "he will drive", "lithuanian": "jis važiuos"},
      "3sg_f_fut": {"english": "she will drive", "lithuanian": "ji važiuos"},
      "1pl_fut": {"english": "we will drive", "lithuanian": "mes važiuosime"},
      "2pl_fut": {"english": "you(pl.) will drive", "lithuanian": "jūs važiuosite"},
      "3pl_m_fut": {"english": "they(m.) will drive", "lithuanian": "jie važiuos"},
      "3pl_f_fut": {"english": "they(f.) will drive", "lithuanian": "jos važiuos"}
    },
    "english_alternatives": ["travel"],
    "tags": ["movement", "transportation", "vehicle"]
  },

  {
    "guid": "V01_021",
    "base_lithuanian": "bėgti",
    "base_english": "to run",
    "corpus": "Verbs",
    "group": "movement_travel",
    "level": 1,
    "word_type": "verb",
    "grammatical_forms": {
      "1sg_pres": {"english": "I run", "lithuanian": "aš bėgu"},
      "2sg_pres": {"english": "you(s.) run", "lithuanian": "tu bėgi"},
      "3sg_m_pres": {"english": "he runs", "lithuanian": "jis bėga"},
      "3sg_f_pres": {"english": "she runs", "lithuanian": "ji bėga"},
      "1pl_pres": {"english": "we run", "lithuanian": "mes bėgame"},
      "2pl_pres": {"english": "you(pl.) run", "lithuanian": "jūs bėgate"},
      "3pl_m_pres": {"english": "they(m.) run", "lithuanian": "jie bėga"},
      "3pl_f_pres": {"english": "they(f.) run", "lithuanian": "jos bėga"},
      "1sg_past": {"english": "I ran", "lithuanian": "aš bėgau"},
      "2sg_past": {"english": "you(s.) ran", "lithuanian": "tu bėgai"},
      "3sg_m_past": {"english": "he ran", "lithuanian": "jis bėgo"},
      "3sg_f_past": {"english": "she ran", "lithuanian": "ji bėgo"},
      "1pl_past": {"english": "we ran", "lithuanian": "mes bėgome"},
      "2pl_past": {"english": "you(pl.) ran", "lithuanian": "jūs bėgote"},
      "3pl_m_past": {"english": "they(m.) ran", "lithuanian": "jie bėgo"},
      "3pl_f_past": {"english": "they(f.) ran", "lithuanian": "jos bėgo"},
      "1sg_fut": {"english": "I will run", "lithuanian": "aš bėgsiu"},
      "2sg_fut": {"english": "you(s.) will run", "lithuanian": "tu bėgsi"},
      "3sg_m_fut": {"english": "he will run", "lithuanian": "jis bėgs"},
      "3sg_f_fut": {"english": "she will run", "lithuanian": "ji bėgs"},
      "1pl_fut": {"english": "we will run", "lithuanian": "mes bėgsime"},
      "2pl_fut": {"english": "you(pl.) will run", "lithuanian": "jūs bėgsite"},
      "3pl_m_fut": {"english": "they(m.) will run", "lithuanian": "jie bėgs"},
      "3pl_f_fut": {"english": "they(f.) will run", "lithuanian": "jos bėgs"}
    },
    "tags": ["movement", "exercise", "speed"]
  },

  {
    "guid": "V01_022",
    "base_lithuanian": "vykti",
    "base_english": "to go",
    "corpus": "Verbs",
    "group": "movement_travel",
    "level": 1,
    "word_type": "verb",
    "grammatical_forms": {
      "1sg_pres": {"english": "I go", "lithuanian": "aš vykstu"},
      "2sg_pres": {"english": "you(s.) go", "lithuanian": "tu vyksti"},
      "3sg_m_pres": {"english": "he goes", "lithuanian": "jis vyksta"},
      "3sg_f_pres": {"english": "she goes", "lithuanian": "ji vyksta"},
      "1pl_pres": {"english": "we go", "lithuanian": "mes vykstame"},
      "2pl_pres": {"english": "you(pl.) go", "lithuanian": "jūs vykstate"},
      "3pl_m_pres": {"english": "they(m.) go", "lithuanian": "jie vyksta"},
      "3pl_f_pres": {"english": "they(f.) go", "lithuanian": "jos vyksta"},
      "1sg_past": {"english": "I went", "lithuanian": "aš vykau"},
      "2sg_past": {"english": "you(s.) went", "lithuanian": "tu vykai"},
      "3sg_m_past": {"english": "he went", "lithuanian": "jis vyko"},
      "3sg_f_past": {"english": "she went", "lithuanian": "ji vyko"},
      "1pl_past": {"english": "we went", "lithuanian": "mes vykome"},
      "2pl_past": {"english": "you(pl.) went", "lithuanian": "jūs vykote"},
      "3pl_m_past": {"english": "they(m.) went", "lithuanian": "jie vyko"},
      "3pl_f_past": {"english": "they(f.) went", "lithuanian": "jos vyko"},
      "1sg_fut": {"english": "I will go", "lithuanian": "aš vyksiu"},
      "2sg_fut": {"english": "you(s.) will go", "lithuanian": "tu vyksi"},
      "3sg_m_fut": {"english": "he will go", "lithuanian": "jis vyks"},
      "3sg_f_fut": {"english": "she will go", "lithuanian": "ji vyks"},
      "1pl_fut": {"english": "we will go", "lithuanian": "mes vyksime"},
      "2pl_fut": {"english": "you(pl.) will go", "lithuanian": "jūs vyksite"},
      "3pl_m_fut": {"english": "they(m.) will go", "lithuanian": "jie vyks"},
      "3pl_f_fut": {"english": "they(f.) will go", "lithuanian": "jos vyks"}
    },
    "english_alternatives": ["proceed"],
    "tags": ["movement", "travel", "direction"]
  },

  {
    "guid": "V01_023",
    "base_lithuanian": "ateiti",
    "base_english": "to come",
    "corpus": "Verbs",
    "group": "movement_travel",
    "level": 1,
    "word_type": "verb",
    "grammatical_forms": {
      "1sg_pres": {"english": "I come", "lithuanian": "aš ateinu"},
      "2sg_pres": {"english": "you(s.) come", "lithuanian": "tu ateini"},
      "3sg_m_pres": {"english": "he comes", "lithuanian": "jis ateina"},
      "3sg_f_pres": {"english": "she comes", "lithuanian": "ji ateina"},
      "1pl_pres": {"english": "we come", "lithuanian": "mes ateiname"},
      "2pl_pres": {"english": "you(pl.) come", "lithuanian": "jūs ateinate"},
      "3pl_m_pres": {"english": "they(m.) come", "lithuanian": "jie ateina"},
      "3pl_f_pres": {"english": "they(f.) come", "lithuanian": "jos ateina"},
      "1sg_past": {"english": "I came", "lithuanian": "aš atėjau"},
      "2sg_past": {"english": "you(s.) came", "lithuanian": "tu atėjai"},
      "3sg_m_past": {"english": "he came", "lithuanian": "jis atėjo"},
      "3sg_f_past": {"english": "she came", "lithuanian": "ji atėjo"},
      "1pl_past": {"english": "we came", "lithuanian": "mes atėjome"},
      "2pl_past": {"english": "you(pl.) came", "lithuanian": "jūs atėjote"},
      "3pl_m_past": {"english": "they(m.) came", "lithuanian": "jie atėjo"},
      "3pl_f_past": {"english": "they(f.) came", "lithuanian": "jos atėjo"},
      "1sg_fut": {"english": "I will come", "lithuanian": "aš ateisiu"},
      "2sg_fut": {"english": "you(s.) will come", "lithuanian": "tu ateisi"},
      "3sg_m_fut": {"english": "he will come", "lithuanian": "jis ateis"},
      "3sg_f_fut": {"english": "she will come", "lithuanian": "ji ateis"},
      "1pl_fut": {"english": "we will come", "lithuanian": "mes ateisime"},
      "2pl_fut": {"english": "you(pl.) will come", "lithuanian": "jūs ateisite"},
      "3pl_m_fut": {"english": "they(m.) will come", "lithuanian": "jie ateis"},
      "3pl_f_fut": {"english": "they(f.) will come", "lithuanian": "jos ateis"}
    },
    "tags": ["movement", "arrival", "direction"]
  },

  {
    "guid": "V01_024",
    "base_lithuanian": "grįžti",
    "base_english": "to return",
    "corpus": "Verbs",
    "group": "movement_travel",
    "level": 1,
    "word_type": "verb",
    "grammatical_forms": {
      "1sg_pres": {"english": "I return", "lithuanian": "aš grįžtu"},
      "2sg_pres": {"english": "you(s.) return", "lithuanian": "tu grįžti"},
      "3sg_m_pres": {"english": "he returns", "lithuanian": "jis grįžta"},
      "3sg_f_pres": {"english": "she returns", "lithuanian": "ji grįžta"},
      "1pl_pres": {"english": "we return", "lithuanian": "mes grįžtame"},
      "2pl_pres": {"english": "you(pl.) return", "lithuanian": "jūs grįžtate"},
      "3pl_m_pres": {"english": "they(m.) return", "lithuanian": "jie grįžta"},
      "3pl_f_pres": {"english": "they(f.) return", "lithuanian": "jos grįžta"},
      "1sg_past": {"english": "I returned", "lithuanian": "aš grįžau"},
      "2sg_past": {"english": "you(s.) returned", "lithuanian": "tu grįžai"},
      "3sg_m_past": {"english": "he returned", "lithuanian": "jis grįžo"},
      "3sg_f_past": {"english": "she returned", "lithuanian": "ji grįžo"},
      "1pl_past": {"english": "we returned", "lithuanian": "mes grįžome"},
      "2pl_past": {"english": "you(pl.) returned", "lithuanian": "jūs grįžote"},
      "3pl_m_past": {"english": "they(m.) returned", "lithuanian": "jie grįžo"},
      "3pl_f_past": {"english": "they(f.) returned", "lithuanian": "jos grįžo"},
      "1sg_fut": {"english": "I will return", "lithuanian": "aš grįšiu"},
      "2sg_fut": {"english": "you(s.) will return", "lithuanian": "tu grįši"},
      "3sg_m_fut": {"english": "he will return", "lithuanian": "jis grįš"},
      "3sg_f_fut": {"english": "she will return", "lithuanian": "ji grįš"},
      "1pl_fut": {"english": "we will return", "lithuanian": "mes grįšime"},
      "2pl_fut": {"english": "you(pl.) will return", "lithuanian": "jūs grįšite"},
      "3pl_m_fut": {"english": "they(m.) will return", "lithuanian": "jie grįš"},
      "3pl_f_fut": {"english": "they(f.) will return", "lithuanian": "jos grįš"}
    },
    "tags": ["movement", "return", "direction"]
  },

  {
    "guid": "V01_025",
    "base_lithuanian": "kalbėti",
    "base_english": "to speak",
    "corpus": "Verbs",
    "group": "sensory_perception",
    "level": 1,
    "word_type": "verb",
    "grammatical_forms": {
      "1sg_pres": {"english": "I speak", "lithuanian": "aš kalbu"},
      "2sg_pres": {"english": "you(s.) speak", "lithuanian": "tu kalbi"},
      "3sg_m_pres": {"english": "he speaks", "lithuanian": "jis kalba"},
      "3sg_f_pres": {"english": "she speaks", "lithuanian": "ji kalba"},
      "1pl_pres": {"english": "we speak", "lithuanian": "mes kalbame"},
      "2pl_pres": {"english": "you(pl.) speak", "lithuanian": "jūs kalbate"},
      "3pl_m_pres": {"english": "they(m.) speak", "lithuanian": "jie kalba"},
      "3pl_f_pres": {"english": "they(f.) speak", "lithuanian": "jos kalba"},
      "1sg_past": {"english": "I spoke", "lithuanian": "aš kalbėjau"},
      "2sg_past": {"english": "you(s.) spoke", "lithuanian": "tu kalbėjai"},
      "3sg_m_past": {"english": "he spoke", "lithuanian": "jis kalbėjo"},
      "3sg_f_past": {"english": "she spoke", "lithuanian": "ji kalbėjo"},
      "1pl_past": {"english": "we spoke", "lithuanian": "mes kalbėjome"},
      "2pl_past": {"english": "you(pl.) spoke", "lithuanian": "jūs kalbėjote"},
      "3pl_m_past": {"english": "they(m.) spoke", "lithuanian": "jie kalbėjo"},
      "3pl_f_past": {"english": "they(f.) spoke", "lithuanian": "jos kalbėjo"},
      "1sg_fut": {"english": "I will speak", "lithuanian": "aš kalbėsiu"},
      "2sg_fut": {"english": "you(s.) will speak", "lithuanian": "tu kalbėsi"},
      "3sg_m_fut": {"english": "he will speak", "lithuanian": "jis kalbės"},
      "3sg_f_fut": {"english": "she will speak", "lithuanian": "ji kalbės"},
      "1pl_fut": {"english": "we will speak", "lithuanian": "mes kalbėsime"},
      "2pl_fut": {"english": "you(pl.) will speak", "lithuanian": "jūs kalbėsite"},
      "3pl_m_fut": {"english": "they(m.) will speak", "lithuanian": "jie kalbės"},
      "3pl_f_fut": {"english": "they(f.) will speak", "lithuanian": "jos kalbės"}
    },
    "tags": ["communication", "language", "expression"]
  },

  {
    "guid": "V01_026",
    "base_lithuanian": "žinoti",
    "base_english": "to know",
    "corpus": "Verbs",
    "group": "mental_emotional",
    "level": 1,
    "word_type": "verb",
    "grammatical_forms": {
      "1sg_pres": {"english": "I know", "lithuanian": "aš žinau"},
      "2sg_pres": {"english": "you(s.) know", "lithuanian": "tu žinai"},
      "3sg_m_pres": {"english": "he knows", "lithuanian": "jis žino"},
      "3sg_f_pres": {"english": "she knows", "lithuanian": "ji žino"},
      "1pl_pres": {"english": "we know", "lithuanian": "mes žinome"},
      "2pl_pres": {"english": "you(pl.) know", "lithuanian": "jūs žinote"},
      "3pl_m_pres": {"english": "they(m.) know", "lithuanian": "jie žino"},
      "3pl_f_pres": {"english": "they(f.) know", "lithuanian": "jos žino"},
      "1sg_past": {"english": "I knew", "lithuanian": "aš žinojau"},
      "2sg_past": {"english": "you(s.) knew", "lithuanian": "tu žinojai"},
      "3sg_m_past": {"english": "he knew", "lithuanian": "jis žinojo"},
      "3sg_f_past": {"english": "she knew", "lithuanian": "ji žinojo"},
      "1pl_past": {"english": "we knew", "lithuanian": "mes žinojome"},
      "2pl_past": {"english": "you(pl.) knew", "lithuanian": "jūs žinojote"},
      "3pl_m_past": {"english": "they(m.) knew", "lithuanian": "jie žinojo"},
      "3pl_f_past": {"english": "they(f.) knew", "lithuanian": "jos žinojo"},
      "1sg_fut": {"english": "I will know", "lithuanian": "aš žinosiu"},
      "2sg_fut": {"english": "you(s.) will know", "lithuanian": "tu žinosi"},
      "3sg_m_fut": {"english": "he will know", "lithuanian": "jis žinos"},
      "3sg_f_fut": {"english": "she will know", "lithuanian": "ji žinos"},
      "1pl_fut": {"english": "we will know", "lithuanian": "mes žinosime"},
      "2pl_fut": {"english": "you(pl.) will know", "lithuanian": "jūs žinosite"},
      "3pl_m_fut": {"english": "they(m.) will know", "lithuanian": "jie žinos"},
      "3pl_f_fut": {"english": "they(f.) will know", "lithuanian": "jos žinos"}
    },
    "tags": ["knowledge", "cognition", "understanding"]
  },

  {
    "guid": "V01_027",
    "base_lithuanian": "galėti",
    "base_english": "to be able",
    "corpus": "Verbs",
    "group": "mental_emotional",
    "level": 1,
    "word_type": "verb",
    "grammatical_forms": {
      "1sg_pres": {"english": "I can", "lithuanian": "aš galiu"},
      "2sg_pres": {"english": "you(s.) can", "lithuanian": "tu gali"},
      "3sg_m_pres": {"english": "he can", "lithuanian": "jis gali"},
      "3sg_f_pres": {"english": "she can", "lithuanian": "ji gali"},
      "1pl_pres": {"english": "we can", "lithuanian": "mes galime"},
      "2pl_pres": {"english": "you(pl.) can", "lithuanian": "jūs galite"},
      "3pl_m_pres": {"english": "they(m.) can", "lithuanian": "jie gali"},
      "3pl_f_pres": {"english": "they(f.) can", "lithuanian": "jos gali"},
      "1sg_past": {"english": "I could", "lithuanian": "aš galėjau"},
      "2sg_past": {"english": "you(s.) could", "lithuanian": "tu galėjai"},
      "3sg_m_past": {"english": "he could", "lithuanian": "jis galėjo"},
      "3sg_f_past": {"english": "she could", "lithuanian": "ji galėjo"},
      "1pl_past": {"english": "we could", "lithuanian": "mes galėjome"},
      "2pl_past": {"english": "you(pl.) could", "lithuanian": "jūs galėjote"},
      "3pl_m_past": {"english": "they(m.) could", "lithuanian": "jie galėjo"},
      "3pl_f_past": {"english": "they(f.) could", "lithuanian": "jos galėjo"},
      "1sg_fut": {"english": "I will be able", "lithuanian": "aš galėsiu"},
      "2sg_fut": {"english": "you(s.) will be able", "lithuanian": "tu galėsi"},
      "3sg_m_fut": {"english": "he will be able", "lithuanian": "jis galės"},
      "3sg_f_fut": {"english": "she will be able", "lithuanian": "ji galės"},
      "1pl_fut": {"english": "we will be able", "lithuanian": "mes galėsime"},
      "2pl_fut": {"english": "you(pl.) will be able", "lithuanian": "jūs galėsite"},
      "3pl_m_fut": {"english": "they(m.) will be able", "lithuanian": "jie galės"},
      "3pl_f_fut": {"english": "they(f.) will be able", "lithuanian": "jos galės"}
    },
    "english_alternatives": ["can"],
    "tags": ["ability", "modal", "auxiliary"]
  },

  {
    "guid": "V01_028",
    "base_lithuanian": "norėti",
    "base_english": "to want",
    "corpus": "Verbs",
    "group": "mental_emotional",
    "level": 1,
    "word_type": "verb",
    "grammatical_forms": {
      "1sg_pres": {"english": "I want", "lithuanian": "aš noriu"},
      "2sg_pres": {"english": "you(s.) want", "lithuanian": "tu nori"},
      "3sg_m_pres": {"english": "he wants", "lithuanian": "jis nori"},
      "3sg_f_pres": {"english": "she wants", "lithuanian": "ji nori"},
      "1pl_pres": {"english": "we want", "lithuanian": "mes norime"},
      "2pl_pres": {"english": "you(pl.) want", "lithuanian": "jūs norite"},
      "3pl_m_pres": {"english": "they(m.) want", "lithuanian": "jie nori"},
      "3pl_f_pres": {"english": "they(f.) want", "lithuanian": "jos nori"},
      "1sg_past": {"english": "I wanted", "lithuanian": "aš norėjau"},
      "2sg_past": {"english": "you(s.) wanted", "lithuanian": "tu norėjai"},
      "3sg_m_past": {"english": "he wanted", "lithuanian": "jis norėjo"},
      "3sg_f_past": {"english": "she wanted", "lithuanian": "ji norėjo"},
      "1pl_past": {"english": "we wanted", "lithuanian": "mes norėjome"},
      "2pl_past": {"english": "you(pl.) wanted", "lithuanian": "jūs norėjote"},
      "3pl_m_past": {"english": "they(m.) wanted", "lithuanian": "jie norėjo"},
      "3pl_f_past": {"english": "they(f.) wanted", "lithuanian": "jos norėjo"},
      "1sg_fut": {"english": "I will want", "lithuanian": "aš norėsiu"},
      "2sg_fut": {"english": "you(s.) will want", "lithuanian": "tu norėsi"},
      "3sg_m_fut": {"english": "he will want", "lithuanian": "jis norės"},
      "3sg_f_fut": {"english": "she will want", "lithuanian": "ji norės"},
      "1pl_fut": {"english": "we will want", "lithuanian": "mes norėsime"},
      "2pl_fut": {"english": "you(pl.) will want", "lithuanian": "jūs norėsite"},
      "3pl_m_fut": {"english": "they(m.) will want", "lithuanian": "jie norės"},
      "3pl_f_fut": {"english": "they(f.) will want", "lithuanian": "jos norės"}
    },
    "tags": ["desire", "intention", "emotion"]
  },

  {
    "guid": "V01_029",
    "base_lithuanian": "matyti",
    "base_english": "to see",
    "corpus": "Verbs",
    "group": "sensory_perception",
    "level": 1,
    "word_type": "verb",
    "grammatical_forms": {
      "1sg_pres": {"english": "I see", "lithuanian": "aš matau"},
      "2sg_pres": {"english": "you(s.) see", "lithuanian": "tu matai"},
      "3sg_m_pres": {"english": "he sees", "lithuanian": "jis mato"},
      "3sg_f_pres": {"english": "she sees", "lithuanian": "ji mato"},
      "1pl_pres": {"english": "we see", "lithuanian": "mes matome"},
      "2pl_pres": {"english": "you(pl.) see", "lithuanian": "jūs matote"},
      "3pl_m_pres": {"english": "they(m.) see", "lithuanian": "jie mato"},
      "3pl_f_pres": {"english": "they(f.) see", "lithuanian": "jos mato"},
      "1sg_past": {"english": "I saw", "lithuanian": "aš mačiau"},
      "2sg_past": {"english": "you(s.) saw", "lithuanian": "tu matei"},
      "3sg_m_past": {"english": "he saw", "lithuanian": "jis matė"},
      "3sg_f_past": {"english": "she saw", "lithuanian": "ji matė"},
      "1pl_past": {"english": "we saw", "lithuanian": "mes matėme"},
      "2pl_past": {"english": "you(pl.) saw", "lithuanian": "jūs matėte"},
      "3pl_m_past": {"english": "they(m.) saw", "lithuanian": "jie matė"},
      "3pl_f_past": {"english": "they(f.) saw", "lithuanian": "jos matė"},
      "1sg_fut": {"english": "I will see", "lithuanian": "aš matysiu"},
      "2sg_fut": {"english": "you(s.) will see", "lithuanian": "tu matysi"},
      "3sg_m_fut": {"english": "he will see", "lithuanian": "jis matys"},
      "3sg_f_fut": {"english": "she will see", "lithuanian": "ji matys"},
      "1pl_fut": {"english": "we will see", "lithuanian": "mes matysime"},
      "2pl_fut": {"english": "you(pl.) will see", "lithuanian": "jūs matysite"},
      "3pl_m_fut": {"english": "they(m.) will see", "lithuanian": "jie matys"},
      "3pl_f_fut": {"english": "they(f.) will see", "lithuanian": "jos matys"}
    },
    "tags": ["perception", "vision", "senses"]
  }
]

# Helper functions for backward compatibility and convenience

def get_wireword_verbs():
    """
    Get all verbs in WireWord format.
    
    Returns:
        list: List of WireWord verb objects
    """
    return wireword_verbs

def get_verb_by_guid(guid):
    """
    Get a specific verb by its GUID.
    
    Args:
        guid (str): The GUID of the verb
        
    Returns:
        dict: WireWord verb object or None if not found
    """
    for verb in wireword_verbs:
        if verb['guid'] == guid:
            return verb
    return None

def get_verbs_by_group(group):
    """
    Get all verbs in a specific group.
    
    Args:
        group (str): The group name
        
    Returns:
        list: List of WireWord verb objects in the specified group
    """
    return [verb for verb in wireword_verbs if verb['group'] == group]

def get_verbs_by_level(level):
    """
    Get all verbs at a specific level.
    
    Args:
        level (int): The difficulty level
        
    Returns:
        list: List of WireWord verb objects at the specified level
    """
    return [verb for verb in wireword_verbs if verb['level'] == level]

def get_all_groups():
    """
    Get all unique group names.
    
    Returns:
        list: List of unique group names
    """
    return list(set(verb['group'] for verb in wireword_verbs))

def get_all_guids():
    """
    Get all verb GUIDs.
    
    Returns:
        list: List of all verb GUIDs
    """
    return [verb['guid'] for verb in wireword_verbs]

# For backward compatibility with the old structure
verbs_new = {
    verb['base_lithuanian']: {
        'english': verb['base_english'],
        'present_tense': {k.split('_')[0] + 's' if k.split('_')[0] in ['1', '2', '3'] else k.replace('_pres', ''): 
                         {'english': v['english'], 'lithuanian': v['lithuanian']} 
                         for k, v in verb['grammatical_forms'].items() if k.endswith('_pres')},
        'past_tense': {k.split('_')[0] + 's' if k.split('_')[0] in ['1', '2', '3'] else k.replace('_past', ''): 
                      {'english': v['english'], 'lithuanian': v['lithuanian']} 
                      for k, v in verb['grammatical_forms'].items() if k.endswith('_past')},
        'future': {k.split('_')[0] + 's' if k.split('_')[0] in ['1', '2', '3'] else k.replace('_fut', ''): 
                  {'english': v['english'], 'lithuanian': v['lithuanian']} 
                  for k, v in verb['grammatical_forms'].items() if k.endswith('_fut')}
    }
    for verb in wireword_verbs
}
