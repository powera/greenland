#!/usr/bin/python3

"""
Restructured verb conjugations for Trakaido Lithuanian learning app.
Each verb is organized by infinitive with all tenses grouped together.
"""

# New verb structure with table format - all verbs organized by infinitive
verbs_new = {
  "valgyti": {
    "english": "to eat",
    "present_tense": {
      "1s": {"english": "I eat", "lithuanian": "aš valgau"},
      "2s": {"english": "you(s.) eat", "lithuanian": "tu valgai"},
      "3s-m": {"english": "he eats", "lithuanian": "jis valgo"},
      "3s-f": {"english": "she eats", "lithuanian": "ji valgo"},
      "1p": {"english": "we eat", "lithuanian": "mes valgome"},
      "2p": {"english": "you(pl.) eat", "lithuanian": "jūs valgote"},
      "3p-m": {"english": "they(m.) eat", "lithuanian": "jie valgo"},
      "3p-f": {"english": "they(f.) eat", "lithuanian": "jos valgo"}
    },
    "past_tense": {
      "1s": {"english": "I ate", "lithuanian": "aš valgiau"},
      "2s": {"english": "you(s.) ate", "lithuanian": "tu valgei"},
      "3s-m": {"english": "he ate", "lithuanian": "jis valgė"},
      "3s-f": {"english": "she ate", "lithuanian": "ji valgė"},
      "1p": {"english": "we ate", "lithuanian": "mes valgėme"},
      "2p": {"english": "you(pl.) ate", "lithuanian": "jūs valgėte"},
      "3p-m": {"english": "they(m.) ate", "lithuanian": "jie valgė"},
      "3p-f": {"english": "they(f.) ate", "lithuanian": "jos valgė"}
    },
    "future": {
      "1s": {"english": "I will eat", "lithuanian": "aš valgysiu"},
      "2s": {"english": "you(s.) will eat", "lithuanian": "tu valgysi"},
      "3s-m": {"english": "he will eat", "lithuanian": "jis valgys"},
      "3s-f": {"english": "she will eat", "lithuanian": "ji valgys"},
      "1p": {"english": "we will eat", "lithuanian": "mes valgysime"},
      "2p": {"english": "you(pl.) will eat", "lithuanian": "jūs valgysite"},
      "3p-m": {"english": "they(m.) will eat", "lithuanian": "jie valgys"},
      "3p-f": {"english": "they(f.) will eat", "lithuanian": "jos valgys"}
    }
  },
  
  "gyventi": {
    "english": "to live",
    "present_tense": {
      "1s": {"english": "I live", "lithuanian": "aš gyvenu"},
      "2s": {"english": "you(s.) live", "lithuanian": "tu gyveni"},
      "3s-m": {"english": "he lives", "lithuanian": "jis gyvena"},
      "3s-f": {"english": "she lives", "lithuanian": "ji gyvena"},
      "1p": {"english": "we live", "lithuanian": "mes gyvename"},
      "2p": {"english": "you(pl.) live", "lithuanian": "jūs gyvenate"},
      "3p-m": {"english": "they(m.) live", "lithuanian": "jie gyvena"},
      "3p-f": {"english": "they(f.) live", "lithuanian": "jos gyvena"}
    },
    "past_tense": {
      "1s": {"english": "I lived", "lithuanian": "aš gyvenau"},
      "2s": {"english": "you(s.) lived", "lithuanian": "tu gyvenai"},
      "3s-m": {"english": "he lived", "lithuanian": "jis gyveno"},
      "3s-f": {"english": "she lived", "lithuanian": "ji gyveno"},
      "1p": {"english": "we lived", "lithuanian": "mes gyvenome"},
      "2p": {"english": "you(pl.) lived", "lithuanian": "jūs gyvenote"},
      "3p-m": {"english": "they(m.) lived", "lithuanian": "jie gyveno"},
      "3p-f": {"english": "they(f.) lived", "lithuanian": "jos gyveno"}
    },
    "future": {
      "1s": {"english": "I will live", "lithuanian": "aš gyvensiu"},
      "2s": {"english": "you(s.) will live", "lithuanian": "tu gyvensi"},
      "3s-m": {"english": "he will live", "lithuanian": "jis gyvens"},
      "3s-f": {"english": "she will live", "lithuanian": "ji gyvens"},
      "1p": {"english": "we will live", "lithuanian": "mes gyvensime"},
      "2p": {"english": "you(pl.) will live", "lithuanian": "jūs gyvensite"},
      "3p-m": {"english": "they(m.) will live", "lithuanian": "jie gyvens"},
      "3p-f": {"english": "they(f.) will live", "lithuanian": "jos gyvens"}
    }
  },
  
  "mokytis": {
    "english": "to learn",
    "present_tense": {
      "1s": {"english": "I learn", "lithuanian": "aš mokausi"},
      "2s": {"english": "you(s.) learn", "lithuanian": "tu mokais"},
      "3s-m": {"english": "he learns", "lithuanian": "jis mokosi"},
      "3s-f": {"english": "she learns", "lithuanian": "ji mokosi"},
      "1p": {"english": "we learn", "lithuanian": "mes mokomės"},
      "2p": {"english": "you(pl.) learn", "lithuanian": "jūs mokotės"},
      "3p-m": {"english": "they(m.) learn", "lithuanian": "jie mokosi"},
      "3p-f": {"english": "they(f.) learn", "lithuanian": "jos mokosi"}
    },
    "past_tense": {
      "1s": {"english": "I learned", "lithuanian": "aš mokiausi"},
      "2s": {"english": "you(s.) learned", "lithuanian": "tu mokeisi"},
      "3s-m": {"english": "he learned", "lithuanian": "jis mokėsi"},
      "3s-f": {"english": "she learned", "lithuanian": "ji mokėsi"},
      "1p": {"english": "we learned", "lithuanian": "mes mokėmės"},
      "2p": {"english": "you(pl.) learned", "lithuanian": "jūs mokėtės"},
      "3p-m": {"english": "they(m.) learned", "lithuanian": "jie mokėsi"},
      "3p-f": {"english": "they(f.) learned", "lithuanian": "jos mokėsi"}
    },
    "future": {
      "1s": {"english": "I will learn", "lithuanian": "aš mokysiuos"},
      "2s": {"english": "you(s.) will learn", "lithuanian": "tu mokysiesi"},
      "3s-m": {"english": "he will learn", "lithuanian": "jis mokysis"},
      "3s-f": {"english": "she will learn", "lithuanian": "ji mokysis"},
      "1p": {"english": "we will learn", "lithuanian": "mes mokysimės"},
      "2p": {"english": "you(pl.) will learn", "lithuanian": "jūs mokysitės"},
      "3p-m": {"english": "they(m.) will learn", "lithuanian": "jie mokysis"},
      "3p-f": {"english": "they(f.) will learn", "lithuanian": "jos mokysis"}
    }
  },
  
  "mokyti": {
    "english": "to teach",
    "present_tense": {
      "1s": {"english": "I teach", "lithuanian": "aš mokau"},
      "2s": {"english": "you(s.) teach", "lithuanian": "tu mokai"},
      "3s-m": {"english": "he teaches", "lithuanian": "jis moko"},
      "3s-f": {"english": "she teaches", "lithuanian": "ji moko"},
      "1p": {"english": "we teach", "lithuanian": "mes mokome"},
      "2p": {"english": "you(pl.) teach", "lithuanian": "jūs mokote"},
      "3p-m": {"english": "they(m.) teach", "lithuanian": "jie moko"},
      "3p-f": {"english": "they(f.) teach", "lithuanian": "jos moko"}
    },
    "past_tense": {
      "1s": {"english": "I taught", "lithuanian": "aš mokiau"},
      "2s": {"english": "you(s.) taught", "lithuanian": "tu mokei"},
      "3s-m": {"english": "he taught", "lithuanian": "jis mokė"},
      "3s-f": {"english": "she taught", "lithuanian": "ji mokė"},
      "1p": {"english": "we taught", "lithuanian": "mes mokėme"},
      "2p": {"english": "you(pl.) taught", "lithuanian": "jūs mokėte"},
      "3p-m": {"english": "they(m.) taught", "lithuanian": "jie mokė"},
      "3p-f": {"english": "they(f.) taught", "lithuanian": "jos mokė"}
    },
    "future": {
      "1s": {"english": "I will teach", "lithuanian": "aš mokysiu"},
      "2s": {"english": "you(s.) will teach", "lithuanian": "tu mokysi"},
      "3s-m": {"english": "he will teach", "lithuanian": "jis mokys"},
      "3s-f": {"english": "she will teach", "lithuanian": "ji mokys"},
      "1p": {"english": "we will teach", "lithuanian": "mes mokysime"},
      "2p": {"english": "you(pl.) will teach", "lithuanian": "jūs mokysite"},
      "3p-m": {"english": "they(m.) will teach", "lithuanian": "jie mokys"},
      "3p-f": {"english": "they(f.) will teach", "lithuanian": "jos mokys"}
    }
  },
  
  "žaisti": {
    "english": "to play",
    "present_tense": {
      "1s": {"english": "I play", "lithuanian": "aš žaidžiu"},
      "2s": {"english": "you(s.) play", "lithuanian": "tu žaidi"},
      "3s-m": {"english": "he plays", "lithuanian": "jis žaidžia"},
      "3s-f": {"english": "she plays", "lithuanian": "ji žaidžia"},
      "1p": {"english": "we play", "lithuanian": "mes žaidžiame"},
      "2p": {"english": "you(pl.) play", "lithuanian": "jūs žaidžiate"},
      "3p-m": {"english": "they(m.) play", "lithuanian": "jie žaidžia"},
      "3p-f": {"english": "they(f.) play", "lithuanian": "jos žaidžia"}
    },
    "past_tense": {
      "1s": {"english": "I played", "lithuanian": "aš žaidžiau"},
      "2s": {"english": "you(s.) played", "lithuanian": "tu žaidei"},
      "3s-m": {"english": "he played", "lithuanian": "jis žaidė"},
      "3s-f": {"english": "she played", "lithuanian": "ji žaidė"},
      "1p": {"english": "we played", "lithuanian": "mes žaidėme"},
      "2p": {"english": "you(pl.) played", "lithuanian": "jūs žaidėte"},
      "3p-m": {"english": "they(m.) played", "lithuanian": "jie žaidė"},
      "3p-f": {"english": "they(f.) played", "lithuanian": "jos žaidė"}
    },
    "future": {
      "1s": {"english": "I will play", "lithuanian": "aš žaisiu"},
      "2s": {"english": "you(s.) will play", "lithuanian": "tu žaisi"},
      "3s-m": {"english": "he will play", "lithuanian": "jis žais"},
      "3s-f": {"english": "she will play", "lithuanian": "ji žais"},
      "1p": {"english": "we will play", "lithuanian": "mes žaisime"},
      "2p": {"english": "you(pl.) will play", "lithuanian": "jūs žaisite"},
      "3p-m": {"english": "they(m.) will play", "lithuanian": "jie žais"},
      "3p-f": {"english": "they(f.) will play", "lithuanian": "jos žais"}
    }
  },
  
  "skaityti": {
    "english": "to read",
    "present_tense": {
      "1s": {"english": "I read (pres. tense)", "lithuanian": "aš skaitau"},
      "2s": {"english": "you(s.) read (pres. tense)", "lithuanian": "tu skaitai"},
      "3s-m": {"english": "he reads", "lithuanian": "jis skaito"},
      "3s-f": {"english": "she reads", "lithuanian": "ji skaito"},
      "1p": {"english": "we read (pres. tense)", "lithuanian": "mes skaitome"},
      "2p": {"english": "you(pl.) read (pres. tense)", "lithuanian": "jūs skaitote"},
      "3p-m": {"english": "they(m.) read (pres. tense)", "lithuanian": "jie skaito"},
      "3p-f": {"english": "they(f.) read (pres. tense)", "lithuanian": "jos skaito"}
    },
    "past_tense": {
      "1s": {"english": "I read (past tense)", "lithuanian": "aš skaičiau"},
      "2s": {"english": "you(s.) read (past tense)", "lithuanian": "tu skaitei"},
      "3s-m": {"english": "he read (past tense)", "lithuanian": "jis skaitė"},
      "3s-f": {"english": "she read (past tense)", "lithuanian": "ji skaitė"},
      "1p": {"english": "we read (past tense)", "lithuanian": "mes skaitėme"},
      "2p": {"english": "you(pl.) read (past tense)", "lithuanian": "jūs skaitėte"},
      "3p-m": {"english": "they(m.) read (past tense)", "lithuanian": "jie skaitė"},
      "3p-f": {"english": "they(f.) read (past tense)", "lithuanian": "jos skaitė"}
    },
    "future": {
      "1s": {"english": "I will read", "lithuanian": "aš skaitysiu"},
      "2s": {"english": "you(s.) will read", "lithuanian": "tu skaitysi"},
      "3s-m": {"english": "he will read", "lithuanian": "jis skaitys"},
      "3s-f": {"english": "she will read", "lithuanian": "ji skaitys"},
      "1p": {"english": "we will read", "lithuanian": "mes skaitysime"},
      "2p": {"english": "you(pl.) will read", "lithuanian": "jūs skaitysite"},
      "3p-m": {"english": "they(m.) will read", "lithuanian": "jie skaitys"},
      "3p-f": {"english": "they(f.) will read", "lithuanian": "jos skaitys"}
    }
  },
  
  "rašyti": {
    "english": "to write",
    "present_tense": {
      "1s": {"english": "I write", "lithuanian": "aš rašau"},
      "2s": {"english": "you(s.) write", "lithuanian": "tu rašai"},
      "3s-m": {"english": "he writes", "lithuanian": "jis rašo"},
      "3s-f": {"english": "she writes", "lithuanian": "ji rašo"},
      "1p": {"english": "we write", "lithuanian": "mes rašome"},
      "2p": {"english": "you(pl.) write", "lithuanian": "jūs rašote"},
      "3p-m": {"english": "they(m.) write", "lithuanian": "jie rašo"},
      "3p-f": {"english": "they(f.) write", "lithuanian": "jos rašo"}
    },
    "past_tense": {
      "1s": {"english": "I wrote", "lithuanian": "aš rašiau"},
      "2s": {"english": "you(s.) wrote", "lithuanian": "tu rašei"},
      "3s-m": {"english": "he wrote", "lithuanian": "jis rašė"},
      "3s-f": {"english": "she wrote", "lithuanian": "ji rašė"},
      "1p": {"english": "we wrote", "lithuanian": "mes rašėme"},
      "2p": {"english": "you(pl.) wrote", "lithuanian": "jūs rašėte"},
      "3p-m": {"english": "they(m.) wrote", "lithuanian": "jie rašė"},
      "3p-f": {"english": "they(f.) wrote", "lithuanian": "jos rašė"}
    },
    "future": {
      "1s": {"english": "I will write", "lithuanian": "aš rašysiu"},
      "2s": {"english": "you(s.) will write", "lithuanian": "tu rašysi"},
      "3s-m": {"english": "he will write", "lithuanian": "jis rašys"},
      "3s-f": {"english": "she will write", "lithuanian": "ji rašys"},
      "1p": {"english": "we will write", "lithuanian": "mes rašysime"},
      "2p": {"english": "you(pl.) will write", "lithuanian": "jūs rašysite"},
      "3p-m": {"english": "they(m.) will write", "lithuanian": "jie rašys"},
      "3p-f": {"english": "they(f.) will write", "lithuanian": "jos rašys"}
    }
  },
  
  "klausyti": {
    "english": "to listen",
    "present_tense": {
      "1s": {"english": "I listen", "lithuanian": "aš klausau"},
      "2s": {"english": "you(s.) listen", "lithuanian": "tu klausai"},
      "3s-m": {"english": "he listens", "lithuanian": "jis klauso"},
      "3s-f": {"english": "she listens", "lithuanian": "ji klauso"},
      "1p": {"english": "we listen", "lithuanian": "mes klausome"},
      "2p": {"english": "you(pl.) listen", "lithuanian": "jūs klausote"},
      "3p-m": {"english": "they(m.) listen", "lithuanian": "jie klauso"},
      "3p-f": {"english": "they(f.) listen", "lithuanian": "jos klauso"}
    },
    "past_tense": {
      "1s": {"english": "I listened", "lithuanian": "aš klausiau"},
      "2s": {"english": "you(s.) listened", "lithuanian": "tu klausei"},
      "3s-m": {"english": "he listened", "lithuanian": "jis klausė"},
      "3s-f": {"english": "she listened", "lithuanian": "ji klausė"},
      "1p": {"english": "we listened", "lithuanian": "mes klausėme"},
      "2p": {"english": "you(pl.) listened", "lithuanian": "jūs klausėte"},
      "3p-m": {"english": "they(m.) listened", "lithuanian": "jie klausė"},
      "3p-f": {"english": "they(f.) listened", "lithuanian": "jos klausė"}
    },
    "future": {
      "1s": {"english": "I will listen", "lithuanian": "aš klausysiu"},
      "2s": {"english": "you(s.) will listen", "lithuanian": "tu klausysi"},
      "3s-m": {"english": "he will listen", "lithuanian": "jis klausys"},
      "3s-f": {"english": "she will listen", "lithuanian": "ji klausys"},
      "1p": {"english": "we will listen", "lithuanian": "mes klausysime"},
      "2p": {"english": "you(pl.) will listen", "lithuanian": "jūs klausysite"},
      "3p-m": {"english": "they(m.) will listen", "lithuanian": "jie klausys"},
      "3p-f": {"english": "they(f.) will listen", "lithuanian": "jos klausys"}
    }
  },

  "dirbti": {
    "english": "to work",
    "present_tense": {
      "1s": {"english": "I work", "lithuanian": "aš dirbu"},
      "2s": {"english": "you(s.) work", "lithuanian": "tu dirbi"},
      "3s-m": {"english": "he works", "lithuanian": "jis dirba"},
      "3s-f": {"english": "she works", "lithuanian": "ji dirba"},
      "1p": {"english": "we work", "lithuanian": "mes dirbame"},
      "2p": {"english": "you(pl.) work", "lithuanian": "jūs dirbate"},
      "3p-m": {"english": "they(m.) work", "lithuanian": "jie dirba"},
      "3p-f": {"english": "they(f.) work", "lithuanian": "jos dirba"}
    },
    "past_tense": {
      "1s": {"english": "I worked", "lithuanian": "aš dirbau"},
      "2s": {"english": "you(s.) worked", "lithuanian": "tu dirbai"},
      "3s-m": {"english": "he worked", "lithuanian": "jis dirbo"},
      "3s-f": {"english": "she worked", "lithuanian": "ji dirbo"},
      "1p": {"english": "we worked", "lithuanian": "mes dirbome"},
      "2p": {"english": "you(pl.) worked", "lithuanian": "jūs dirbote"},
      "3p-m": {"english": "they(m.) worked", "lithuanian": "jie dirbo"},
      "3p-f": {"english": "they(f.) worked", "lithuanian": "jos dirbo"}
    },
    "future": {
      "1s": {"english": "I will work", "lithuanian": "aš dirbsiu"},
      "2s": {"english": "you(s.) will work", "lithuanian": "tu dirbsi"},
      "3s-m": {"english": "he will work", "lithuanian": "jis dirbs"},
      "3s-f": {"english": "she will work", "lithuanian": "ji dirbs"},
      "1p": {"english": "we will work", "lithuanian": "mes dirbsime"},
      "2p": {"english": "you(pl.) will work", "lithuanian": "jūs dirbsite"},
      "3p-m": {"english": "they(m.) will work", "lithuanian": "jie dirbs"},
      "3p-f": {"english": "they(f.) will work", "lithuanian": "jos dirbs"}
    },
  },
  
  "gerti": {
    "english": "to drink",
    "present_tense": {
      "1s": {"english": "I drink", "lithuanian": "aš geriu"},
      "2s": {"english": "you(s.) drink", "lithuanian": "tu geri"},
      "3s-m": {"english": "he drinks", "lithuanian": "jis geria"},
      "3s-f": {"english": "she drinks", "lithuanian": "ji geria"},
      "1p": {"english": "we drink", "lithuanian": "mes geriame"},
      "2p": {"english": "you(pl.) drink", "lithuanian": "jūs geriate"},
      "3p-m": {"english": "they(m.) drink", "lithuanian": "jie geria"},
      "3p-f": {"english": "they(f.) drink", "lithuanian": "jos geria"}
    },
    "past_tense": {
      "1s": {"english": "I drank", "lithuanian": "aš gėriau"},
      "2s": {"english": "you(s.) drank", "lithuanian": "tu gėrei"},
      "3s-m": {"english": "he drank", "lithuanian": "jis gėrė"},
      "3s-f": {"english": "she drank", "lithuanian": "ji gėrė"},
      "1p": {"english": "we drank", "lithuanian": "mes gėrėme"},
      "2p": {"english": "you(pl.) drank", "lithuanian": "jūs gėrėte"},
      "3p-m": {"english": "they(m.) drank", "lithuanian": "jie gėrė"},
      "3p-f": {"english": "they(f.) drank", "lithuanian": "jos gėrė"}
    },
    "future": {
      "1s": {"english": "I will drink", "lithuanian": "aš gersiu"},
      "2s": {"english": "you(s.) will drink", "lithuanian": "tu gersi"},
      "3s-m": {"english": "he will drink", "lithuanian": "jis gers"},
      "3s-f": {"english": "she will drink", "lithuanian": "ji gers"},
      "1p": {"english": "we will drink", "lithuanian": "mes gersime"},
      "2p": {"english": "you(pl.) will drink", "lithuanian": "jūs gersite"},
      "3p-m": {"english": "they(m.) will drink", "lithuanian": "jie gers"},
      "3p-f": {"english": "they(f.) will drink", "lithuanian": "jos gers"}
    }
  },
  
  "miegoti": {
    "english": "to sleep",
    "present_tense": {
      "1s": {"english": "I sleep", "lithuanian": "aš miegu"},
      "2s": {"english": "you(s.) sleep", "lithuanian": "tu miegi"},
      "3s-m": {"english": "he sleeps", "lithuanian": "jis miega"},
      "3s-f": {"english": "she sleeps", "lithuanian": "ji miega"},
      "1p": {"english": "we sleep", "lithuanian": "mes miegame"},
      "2p": {"english": "you(pl.) sleep", "lithuanian": "jūs miegate"},
      "3p-m": {"english": "they(m.) sleep", "lithuanian": "jie miega"},
      "3p-f": {"english": "they(f.) sleep", "lithuanian": "jos miega"}
    },
    "past_tense": {
      "1s": {"english": "I slept", "lithuanian": "aš miegojau"},
      "2s": {"english": "you(s.) slept", "lithuanian": "tu miegojai"},
      "3s-m": {"english": "he slept", "lithuanian": "jis miegojo"},
      "3s-f": {"english": "she slept", "lithuanian": "ji miegojo"},
      "1p": {"english": "we slept", "lithuanian": "mes miegojome"},
      "2p": {"english": "you(pl.) slept", "lithuanian": "jūs miegojote"},
      "3p-m": {"english": "they(m.) slept", "lithuanian": "jie miegojo"},
      "3p-f": {"english": "they(f.) slept", "lithuanian": "jos miegojo"}
    },
    "future": {
      "1s": {"english": "I will sleep", "lithuanian": "aš miegosiu"},
      "2s": {"english": "you(s.) will sleep", "lithuanian": "tu miegosi"},
      "3s-m": {"english": "he will sleep", "lithuanian": "jis miegos"},
      "3s-f": {"english": "she will sleep", "lithuanian": "ji miegos"},
      "1p": {"english": "we will sleep", "lithuanian": "mes miegosime"},
      "2p": {"english": "you(pl.) will sleep", "lithuanian": "jūs miegosite"},
      "3p-m": {"english": "they(m.) will sleep", "lithuanian": "jie miegos"},
      "3p-f": {"english": "they(f.) will sleep", "lithuanian": "jos miegos"}
    }
  },
  
  "būti": {
    "english": "to be",
    "present_tense": {
      "1s": {"english": "I am", "lithuanian": "aš esu"},
      "2s": {"english": "you(s.) are", "lithuanian": "tu esi"},
      "3s-m": {"english": "he is", "lithuanian": "jis yra"},
      "3s-f": {"english": "she is", "lithuanian": "ji yra"},
      "1p": {"english": "we are", "lithuanian": "mes esame"},
      "2p": {"english": "you(pl.) are", "lithuanian": "jūs esate"},
      "3p-m": {"english": "they(m.) are", "lithuanian": "jie yra"},
      "3p-f": {"english": "they(f.) are", "lithuanian": "jos yra"}
    },
    "past_tense": {
      "1s": {"english": "I was", "lithuanian": "aš buvau"},
      "2s": {"english": "you(s.) were", "lithuanian": "tu buvai"},
      "3s-m": {"english": "he was", "lithuanian": "jis buvo"},
      "3s-f": {"english": "she was", "lithuanian": "ji buvo"},
      "1p": {"english": "we were", "lithuanian": "mes buvome"},
      "2p": {"english": "you(pl.) were", "lithuanian": "jūs buvote"},
      "3p-m": {"english": "they(m.) were", "lithuanian": "jie buvo"},
      "3p-f": {"english": "they(f.) were", "lithuanian": "jos buvo"}
    },
    "future": {
      "1s": {"english": "I will be", "lithuanian": "aš būsiu"},
      "2s": {"english": "you(s.) will be", "lithuanian": "tu būsi"},
      "3s-m": {"english": "he will be", "lithuanian": "jis bus"},
      "3s-f": {"english": "she will be", "lithuanian": "ji bus"},
      "1p": {"english": "we will be", "lithuanian": "mes būsime"},
      "2p": {"english": "you(pl.) will be", "lithuanian": "jūs būsite"},
      "3p-m": {"english": "they(m.) will be", "lithuanian": "jie bus"},
      "3p-f": {"english": "they(f.) will be", "lithuanian": "jos bus"}
    }
  },
  
  "turėti": {
    "english": "to have",
    "present_tense": {
      "1s": {"english": "I have", "lithuanian": "aš turiu"},
      "2s": {"english": "you(s.) have", "lithuanian": "tu turi"},
      "3s-m": {"english": "he has", "lithuanian": "jis turi"},
      "3s-f": {"english": "she has", "lithuanian": "ji turi"},
      "1p": {"english": "we have", "lithuanian": "mes turime"},
      "2p": {"english": "you(pl.) have", "lithuanian": "jūs turite"},
      "3p-m": {"english": "they(m.) have", "lithuanian": "jie turi"},
      "3p-f": {"english": "they(f.) have", "lithuanian": "jos turi"}
    },
    "past_tense": {
      "1s": {"english": "I had", "lithuanian": "aš turėjau"},
      "2s": {"english": "you(s.) had", "lithuanian": "tu turėjai"},
      "3s-m": {"english": "he had", "lithuanian": "jis turėjo"},
      "3s-f": {"english": "she had", "lithuanian": "ji turėjo"},
      "1p": {"english": "we had", "lithuanian": "mes turėjome"},
      "2p": {"english": "you(pl.) had", "lithuanian": "jūs turėjote"},
      "3p-m": {"english": "they(m.) had", "lithuanian": "jie turėjo"},
      "3p-f": {"english": "they(f.) had", "lithuanian": "jos turėjo"}
    },
    "future": {
      "1s": {"english": "I will have", "lithuanian": "aš turėsiu"},
      "2s": {"english": "you(s.) will have", "lithuanian": "tu turėsi"},
      "3s-m": {"english": "he will have", "lithuanian": "jis turės"},
      "3s-f": {"english": "she will have", "lithuanian": "ji turės"},
      "1p": {"english": "we will have", "lithuanian": "mes turėsime"},
      "2p": {"english": "you(pl.) will have", "lithuanian": "jūs turėsite"},
      "3p-m": {"english": "they(m.) will have", "lithuanian": "jie turės"},
      "3p-f": {"english": "they(f.) will have", "lithuanian": "jos turės"}
    }
  },
  
  "mėgti": {
    "english": "to like",
    "present_tense": {
      "1s": {"english": "I like", "lithuanian": "aš mėgstu"},
      "2s": {"english": "you(s.) like", "lithuanian": "tu mėgsti"},
      "3s-m": {"english": "he likes", "lithuanian": "jis mėgsta"},
      "3s-f": {"english": "she likes", "lithuanian": "ji mėgsta"},
      "1p": {"english": "we like", "lithuanian": "mes mėgstame"},
      "2p": {"english": "you(pl.) like", "lithuanian": "jūs mėgstate"},
      "3p-m": {"english": "they(m.) like", "lithuanian": "jie mėgsta"},
      "3p-f": {"english": "they(f.) like", "lithuanian": "jos mėgsta"}
    },
    "past_tense": {
      "1s": {"english": "I liked", "lithuanian": "aš mėgau"},
      "2s": {"english": "you(s.) liked", "lithuanian": "tu mėgai"},
      "3s-m": {"english": "he liked", "lithuanian": "jis mėgo"},
      "3s-f": {"english": "she liked", "lithuanian": "ji mėgo"},
      "1p": {"english": "we liked", "lithuanian": "mes mėgome"},
      "2p": {"english": "you(pl.) liked", "lithuanian": "jūs mėgote"},
      "3p-m": {"english": "they(m.) liked", "lithuanian": "jie mėgo"},
      "3p-f": {"english": "they(f.) liked", "lithuanian": "jos mėgo"}
    },
    "future": {
      "1s": {"english": "I will like", "lithuanian": "aš mėgsiu"},
      "2s": {"english": "you(s.) will like", "lithuanian": "tu mėgsi"},
      "3s-m": {"english": "he will like", "lithuanian": "jis mėgs"},
      "3s-f": {"english": "she will like", "lithuanian": "ji mėgs"},
      "1p": {"english": "we will like", "lithuanian": "mes mėgsime"},
      "2p": {"english": "you(pl.) will like", "lithuanian": "jūs mėgsite"},
      "3p-m": {"english": "they(m.) will like", "lithuanian": "jie mėgs"},
      "3p-f": {"english": "they(f.) will like", "lithuanian": "jos mėgs"}
    }
  },
  
  "gaminti": {
    "english": "to make",
    "present_tense": {
      "1s": {"english": "I make", "lithuanian": "aš gaminu"},
      "2s": {"english": "you(s.) make", "lithuanian": "tu gamini"},
      "3s-m": {"english": "he makes", "lithuanian": "jis gamina"},
      "3s-f": {"english": "she makes", "lithuanian": "ji gamina"},
      "1p": {"english": "we make", "lithuanian": "mes gaminame"},
      "2p": {"english": "you(pl.) make", "lithuanian": "jūs gaminate"},
      "3p-m": {"english": "they(m.) make", "lithuanian": "jie gamina"},
      "3p-f": {"english": "they(f.) make", "lithuanian": "jos gamina"}
    },
    "past_tense": {
      "1s": {"english": "I made", "lithuanian": "aš gaminau"},
      "2s": {"english": "you(s.) made", "lithuanian": "tu gaminai"},
      "3s-m": {"english": "he made", "lithuanian": "jis gamino"},
      "3s-f": {"english": "she made", "lithuanian": "ji gamino"},
      "1p": {"english": "we made", "lithuanian": "mes gaminome"},
      "2p": {"english": "you(pl.) made", "lithuanian": "jūs gaminote"},
      "3p-m": {"english": "they(m.) made", "lithuanian": "jie gamino"},
      "3p-f": {"english": "they(f.) made", "lithuanian": "jos gamino"}
    },
    "future": {
      "1s": {"english": "I will make", "lithuanian": "aš gaminsiu"},
      "2s": {"english": "you(s.) will make", "lithuanian": "tu gaminsi"},
      "3s-m": {"english": "he will make", "lithuanian": "jis gamins"},
      "3s-f": {"english": "she will make", "lithuanian": "ji gamins"},
      "1p": {"english": "we will make", "lithuanian": "mes gaminsime"},
      "2p": {"english": "you(pl.) will make", "lithuanian": "jūs gaminsite"},
      "3p-m": {"english": "they(m.) will make", "lithuanian": "jie gamins"},
      "3p-f": {"english": "they(f.) will make", "lithuanian": "jos gamins"}
    }
  },
  
  "pirkti": {
    "english": "to buy",
    "present_tense": {
      "1s": {"english": "I buy", "lithuanian": "aš perku"},
      "2s": {"english": "you(s.) buy", "lithuanian": "tu perki"},
      "3s-m": {"english": "he buys", "lithuanian": "jis perka"},
      "3s-f": {"english": "she buys", "lithuanian": "ji perka"},
      "1p": {"english": "we buy", "lithuanian": "mes perkame"},
      "2p": {"english": "you(pl.) buy", "lithuanian": "jūs perkate"},
      "3p-m": {"english": "they(m.) buy", "lithuanian": "jie perka"},
      "3p-f": {"english": "they(f.) buy", "lithuanian": "jos perka"}
    },
    "past_tense": {
      "1s": {"english": "I bought", "lithuanian": "aš pirkau"},
      "2s": {"english": "you(s.) bought", "lithuanian": "tu pirkai"},
      "3s-m": {"english": "he bought", "lithuanian": "jis pirko"},
      "3s-f": {"english": "she bought", "lithuanian": "ji pirko"},
      "1p": {"english": "we bought", "lithuanian": "mes pirkome"},
      "2p": {"english": "you(pl.) bought", "lithuanian": "jūs pirkote"},
      "3p-m": {"english": "they(m.) bought", "lithuanian": "jie pirko"},
      "3p-f": {"english": "they(f.) bought", "lithuanian": "jos pirko"}
    },
    "future": {
      "1s": {"english": "I will buy", "lithuanian": "aš pirksiu"},
      "2s": {"english": "you(s.) will buy", "lithuanian": "tu pirksi"},
      "3s-m": {"english": "he will buy", "lithuanian": "jis pirks"},
      "3s-f": {"english": "she will buy", "lithuanian": "ji pirks"},
      "1p": {"english": "we will buy", "lithuanian": "mes pirksime"},
      "2p": {"english": "you(pl.) will buy", "lithuanian": "jūs pirksite"},
      "3p-m": {"english": "they(m.) will buy", "lithuanian": "jie pirks"},
      "3p-f": {"english": "they(f.) will buy", "lithuanian": "jos pirks"}
    }
  },
  
  "duoti": {
    "english": "to give",
    "present_tense": {
      "1s": {"english": "I give", "lithuanian": "aš duodu"},
      "2s": {"english": "you(s.) give", "lithuanian": "tu duodi"},
      "3s-m": {"english": "he gives", "lithuanian": "jis duoda"},
      "3s-f": {"english": "she gives", "lithuanian": "ji duoda"},
      "1p": {"english": "we give", "lithuanian": "mes duodame"},
      "2p": {"english": "you(pl.) give", "lithuanian": "jūs duodate"},
      "3p-m": {"english": "they(m.) give", "lithuanian": "jie duoda"},
      "3p-f": {"english": "they(f.) give", "lithuanian": "jos duoda"}
    },
    "past_tense": {
      "1s": {"english": "I gave", "lithuanian": "aš daviau"},
      "2s": {"english": "you(s.) gave", "lithuanian": "tu davei"},
      "3s-m": {"english": "he gave", "lithuanian": "jis davė"},
      "3s-f": {"english": "she gave", "lithuanian": "ji davė"},
      "1p": {"english": "we gave", "lithuanian": "mes davėme"},
      "2p": {"english": "you(pl.) gave", "lithuanian": "jūs davėte"},
      "3p-m": {"english": "they(m.) gave", "lithuanian": "jie davė"},
      "3p-f": {"english": "they(f.) gave", "lithuanian": "jos davė"}
    },
    "future": {
      "1s": {"english": "I will give", "lithuanian": "aš duosiu"},
      "2s": {"english": "you(s.) will give", "lithuanian": "tu duosi"},
      "3s-m": {"english": "he will give", "lithuanian": "jis duos"},
      "3s-f": {"english": "she will give", "lithuanian": "ji duos"},
      "1p": {"english": "we will give", "lithuanian": "mes duosime"},
      "2p": {"english": "you(pl.) will give", "lithuanian": "jūs duosite"},
      "3p-m": {"english": "they(m.) will give", "lithuanian": "jie duos"},
      "3p-f": {"english": "they(f.) will give", "lithuanian": "jos duos"}
    }
  },
  
  "imti": {
    "english": "to take",
    "present_tense": {
      "1s": {"english": "I take", "lithuanian": "aš imu"},
      "2s": {"english": "you(s.) take", "lithuanian": "tu imi"},
      "3s-m": {"english": "he takes", "lithuanian": "jis ima"},
      "3s-f": {"english": "she takes", "lithuanian": "ji ima"},
      "1p": {"english": "we take", "lithuanian": "mes imame"},
      "2p": {"english": "you(pl.) take", "lithuanian": "jūs imate"},
      "3p-m": {"english": "they(m.) take", "lithuanian": "jie ima"},
      "3p-f": {"english": "they(f.) take", "lithuanian": "jos ima"}
    },
    "past_tense": {
      "1s": {"english": "I took", "lithuanian": "aš ėmiau"},
      "2s": {"english": "you(s.) took", "lithuanian": "tu ėmei"},
      "3s-m": {"english": "he took", "lithuanian": "jis ėmė"},
      "3s-f": {"english": "she took", "lithuanian": "ji ėmė"},
      "1p": {"english": "we took", "lithuanian": "mes ėmėme"},
      "2p": {"english": "you(pl.) took", "lithuanian": "jūs ėmėte"},
      "3p-m": {"english": "they(m.) took", "lithuanian": "jie ėmė"},
      "3p-f": {"english": "they(f.) took", "lithuanian": "jos ėmė"}
    },
    "future": {
      "1s": {"english": "I will take", "lithuanian": "aš imsiu"},
      "2s": {"english": "you(s.) will take", "lithuanian": "tu imsi"},
      "3s-m": {"english": "he will take", "lithuanian": "jis ims"},
      "3s-f": {"english": "she will take", "lithuanian": "ji ims"},
      "1p": {"english": "we will take", "lithuanian": "mes imsime"},
      "2p": {"english": "you(pl.) will take", "lithuanian": "jūs imsite"},
      "3p-m": {"english": "they(m.) will take", "lithuanian": "jie ims"},
      "3p-f": {"english": "they(f.) will take", "lithuanian": "jos ims"}
    }
  },
  
  "eiti": {
    "english": "to walk/go",
    "present_tense": {
      "1s": {"english": "I walk", "lithuanian": "aš einu"},
      "2s": {"english": "you(s.) walk", "lithuanian": "tu eini"},
      "3s-m": {"english": "he walks", "lithuanian": "jis eina"},
      "3s-f": {"english": "she walks", "lithuanian": "ji eina"},
      "1p": {"english": "we walk", "lithuanian": "mes einame"},
      "2p": {"english": "you(pl.) walk", "lithuanian": "jūs einate"},
      "3p-m": {"english": "they(m.) walk", "lithuanian": "jie eina"},
      "3p-f": {"english": "they(f.) walk", "lithuanian": "jos eina"}
    },
    "past_tense": {
      "1s": {"english": "I walked", "lithuanian": "aš ėjau"},
      "2s": {"english": "you(s.) walked", "lithuanian": "tu ėjai"},
      "3s-m": {"english": "he walked", "lithuanian": "jis ėjo"},
      "3s-f": {"english": "she walked", "lithuanian": "ji ėjo"},
      "1p": {"english": "we walked", "lithuanian": "mes ėjome"},
      "2p": {"english": "you(pl.) walked", "lithuanian": "jūs ėjote"},
      "3p-m": {"english": "they(m.) walked", "lithuanian": "jie ėjo"},
      "3p-f": {"english": "they(f.) walked", "lithuanian": "jos ėjo"}
    },
    "future": {
      "1s": {"english": "I will walk", "lithuanian": "aš eisiu"},
      "2s": {"english": "you(s.) will walk", "lithuanian": "tu eisi"},
      "3s-m": {"english": "he will walk", "lithuanian": "jis eis"},
      "3s-f": {"english": "she will walk", "lithuanian": "ji eis"},
      "1p": {"english": "we will walk", "lithuanian": "mes eisime"},
      "2p": {"english": "you(pl.) will walk", "lithuanian": "jūs eisite"},
      "3p-m": {"english": "they(m.) will walk", "lithuanian": "jie eis"},
      "3p-f": {"english": "they(f.) will walk", "lithuanian": "jos eis"}
    }
  },
  
  "važiuoti": {
    "english": "to drive/travel",
    "present_tense": {
      "1s": {"english": "I drive", "lithuanian": "aš važiuoju"},
      "2s": {"english": "you(s.) drive", "lithuanian": "tu važiuoji"},
      "3s-m": {"english": "he drives", "lithuanian": "jis važiuoja"},
      "3s-f": {"english": "she drives", "lithuanian": "ji važiuoja"},
      "1p": {"english": "we drive", "lithuanian": "mes važiuojame"},
      "2p": {"english": "you(pl.) drive", "lithuanian": "jūs važiuojate"},
      "3p-m": {"english": "they(m.) drive", "lithuanian": "jie važiuoja"},
      "3p-f": {"english": "they(f.) drive", "lithuanian": "jos važiuoja"}
    },
    "past_tense": {
      "1s": {"english": "I drove", "lithuanian": "aš važiavau"},
      "2s": {"english": "you(s.) drove", "lithuanian": "tu važiavai"},
      "3s-m": {"english": "he drove", "lithuanian": "jis važiavo"},
      "3s-f": {"english": "she drove", "lithuanian": "ji važiavo"},
      "1p": {"english": "we drove", "lithuanian": "mes važiavome"},
      "2p": {"english": "you(pl.) drove", "lithuanian": "jūs važiavote"},
      "3p-m": {"english": "they(m.) drove", "lithuanian": "jie važiavo"},
      "3p-f": {"english": "they(f.) drove", "lithuanian": "jos važiavo"}
    },
    "future": {
      "1s": {"english": "I will drive", "lithuanian": "aš važiuosiu"},
      "2s": {"english": "you(s.) will drive", "lithuanian": "tu važiuosi"},
      "3s-m": {"english": "he will drive", "lithuanian": "jis važiuos"},
      "3s-f": {"english": "she will drive", "lithuanian": "ji važiuos"},
      "1p": {"english": "we will drive", "lithuanian": "mes važiuosime"},
      "2p": {"english": "you(pl.) will drive", "lithuanian": "jūs važiuosite"},
      "3p-m": {"english": "they(m.) will drive", "lithuanian": "jie važiuos"},
      "3p-f": {"english": "they(f.) will drive", "lithuanian": "jos važiuos"}
    }
  },
  
  "bėgti": {
    "english": "to run",
    "present_tense": {
      "1s": {"english": "I run", "lithuanian": "aš bėgu"},
      "2s": {"english": "you(s.) run", "lithuanian": "tu bėgi"},
      "3s-m": {"english": "he runs", "lithuanian": "jis bėga"},
      "3s-f": {"english": "she runs", "lithuanian": "ji bėga"},
      "1p": {"english": "we run", "lithuanian": "mes bėgame"},
      "2p": {"english": "you(pl.) run", "lithuanian": "jūs bėgate"},
      "3p-m": {"english": "they(m.) run", "lithuanian": "jie bėga"},
      "3p-f": {"english": "they(f.) run", "lithuanian": "jos bėga"}
    },
    "past_tense": {
      "1s": {"english": "I ran", "lithuanian": "aš bėgau"},
      "2s": {"english": "you(s.) ran", "lithuanian": "tu bėgai"},
      "3s-m": {"english": "he ran", "lithuanian": "jis bėgo"},
      "3s-f": {"english": "she ran", "lithuanian": "ji bėgo"},
      "1p": {"english": "we ran", "lithuanian": "mes bėgome"},
      "2p": {"english": "you(pl.) ran", "lithuanian": "jūs bėgote"},
      "3p-m": {"english": "they(m.) ran", "lithuanian": "jie bėgo"},
      "3p-f": {"english": "they(f.) ran", "lithuanian": "jos bėgo"}
    },
    "future": {
      "1s": {"english": "I will run", "lithuanian": "aš bėgsiu"},
      "2s": {"english": "you(s.) will run", "lithuanian": "tu bėgsi"},
      "3s-m": {"english": "he will run", "lithuanian": "jis bėgs"},
      "3s-f": {"english": "she will run", "lithuanian": "ji bėgs"},
      "1p": {"english": "we will run", "lithuanian": "mes bėgsime"},
      "2p": {"english": "you(pl.) will run", "lithuanian": "jūs bėgsite"},
      "3p-m": {"english": "they(m.) will run", "lithuanian": "jie bėgs"},
      "3p-f": {"english": "they(f.) will run", "lithuanian": "jos bėgs"}
    }
  },
  
  "vykti": {
    "english": "to go/proceed",
    "present_tense": {
      "1s": {"english": "I go", "lithuanian": "aš vykstu"},
      "2s": {"english": "you(s.) go", "lithuanian": "tu vyksti"},
      "3s-m": {"english": "he goes", "lithuanian": "jis vyksta"},
      "3s-f": {"english": "she goes", "lithuanian": "ji vyksta"},
      "1p": {"english": "we go", "lithuanian": "mes vykstame"},
      "2p": {"english": "you(pl.) go", "lithuanian": "jūs vykstate"},
      "3p-m": {"english": "they(m.) go", "lithuanian": "jie vyksta"},
      "3p-f": {"english": "they(f.) go", "lithuanian": "jos vyksta"}
    },
    "past_tense": {
      "1s": {"english": "I went", "lithuanian": "aš vykau"},
      "2s": {"english": "you(s.) went", "lithuanian": "tu vykai"},
      "3s-m": {"english": "he went", "lithuanian": "jis vyko"},
      "3s-f": {"english": "she went", "lithuanian": "ji vyko"},
      "1p": {"english": "we went", "lithuanian": "mes vykome"},
      "2p": {"english": "you(pl.) went", "lithuanian": "jūs vykote"},
      "3p-m": {"english": "they(m.) went", "lithuanian": "jie vyko"},
      "3p-f": {"english": "they(f.) went", "lithuanian": "jos vyko"}
    },
    "future": {
      "1s": {"english": "I will go", "lithuanian": "aš vyksiu"},
      "2s": {"english": "you(s.) will go", "lithuanian": "tu vyksi"},
      "3s-m": {"english": "he will go", "lithuanian": "jis vyks"},
      "3s-f": {"english": "she will go", "lithuanian": "ji vyks"},
      "1p": {"english": "we will go", "lithuanian": "mes vyksime"},
      "2p": {"english": "you(pl.) will go", "lithuanian": "jūs vyksite"},
      "3p-m": {"english": "they(m.) will go", "lithuanian": "jie vyks"},
      "3p-f": {"english": "they(f.) will go", "lithuanian": "jos vyks"}
    }
  },
  
  "ateiti": {
    "english": "to come",
    "present_tense": {
      "1s": {"english": "I come", "lithuanian": "aš ateinu"},
      "2s": {"english": "you(s.) come", "lithuanian": "tu ateini"},
      "3s-m": {"english": "he comes", "lithuanian": "jis ateina"},
      "3s-f": {"english": "she comes", "lithuanian": "ji ateina"},
      "1p": {"english": "we come", "lithuanian": "mes ateiname"},
      "2p": {"english": "you(pl.) come", "lithuanian": "jūs ateinate"},
      "3p-m": {"english": "they(m.) come", "lithuanian": "jie ateina"},
      "3p-f": {"english": "they(f.) come", "lithuanian": "jos ateina"}
    },
    "past_tense": {
      "1s": {"english": "I came", "lithuanian": "aš atėjau"},
      "2s": {"english": "you(s.) came", "lithuanian": "tu atėjai"},
      "3s-m": {"english": "he came", "lithuanian": "jis atėjo"},
      "3s-f": {"english": "she came", "lithuanian": "ji atėjo"},
      "1p": {"english": "we came", "lithuanian": "mes atėjome"},
      "2p": {"english": "you(pl.) came", "lithuanian": "jūs atėjote"},
      "3p-m": {"english": "they(m.) came", "lithuanian": "jie atėjo"},
      "3p-f": {"english": "they(f.) came", "lithuanian": "jos atėjo"}
    },
    "future": {
      "1s": {"english": "I will come", "lithuanian": "aš ateisiu"},
      "2s": {"english": "you(s.) will come", "lithuanian": "tu ateisi"},
      "3s-m": {"english": "he will come", "lithuanian": "jis ateis"},
      "3s-f": {"english": "she will come", "lithuanian": "ji ateis"},
      "1p": {"english": "we will come", "lithuanian": "mes ateisime"},
      "2p": {"english": "you(pl.) will come", "lithuanian": "jūs ateisite"},
      "3p-m": {"english": "they(m.) will come", "lithuanian": "jie ateis"},
      "3p-f": {"english": "they(f.) will come", "lithuanian": "jos ateis"}
    }
  },
  
  "grįžti": {
    "english": "to return",
    "present_tense": {
      "1s": {"english": "I return", "lithuanian": "aš grįžtu"},
      "2s": {"english": "you(s.) return", "lithuanian": "tu grįžti"},
      "3s-m": {"english": "he returns", "lithuanian": "jis grįžta"},
      "3s-f": {"english": "she returns", "lithuanian": "ji grįžta"},
      "1p": {"english": "we return", "lithuanian": "mes grįžtame"},
      "2p": {"english": "you(pl.) return", "lithuanian": "jūs grįžtate"},
      "3p-m": {"english": "they(m.) return", "lithuanian": "jie grįžta"},
      "3p-f": {"english": "they(f.) return", "lithuanian": "jos grįžta"}
    },
    "past_tense": {
      "1s": {"english": "I returned", "lithuanian": "aš grįžau"},
      "2s": {"english": "you(s.) returned", "lithuanian": "tu grįžai"},
      "3s-m": {"english": "he returned", "lithuanian": "jis grįžo"},
      "3s-f": {"english": "she returned", "lithuanian": "ji grįžo"},
      "1p": {"english": "we returned", "lithuanian": "mes grįžome"},
      "2p": {"english": "you(pl.) returned", "lithuanian": "jūs grįžote"},
      "3p-m": {"english": "they(m.) returned", "lithuanian": "jie grįžo"},
      "3p-f": {"english": "they(f.) returned", "lithuanian": "jos grįžo"}
    },
    "future": {
      "1s": {"english": "I will return", "lithuanian": "aš grįšiu"},
      "2s": {"english": "you(s.) will return", "lithuanian": "tu grįši"},
      "3s-m": {"english": "he will return", "lithuanian": "jis grįš"},
      "3s-f": {"english": "she will return", "lithuanian": "ji grįš"},
      "1p": {"english": "we will return", "lithuanian": "mes grįšime"},
      "2p": {"english": "you(pl.) will return", "lithuanian": "jūs grįšite"},
      "3p-m": {"english": "they(m.) will return", "lithuanian": "jie grįš"},
      "3p-f": {"english": "they(f.) will return", "lithuanian": "jos grįš"}
    }
  },
  
  "kalbėti": {
    "english": "to speak",
    "present_tense": {
      "1s": {"english": "I speak", "lithuanian": "aš kalbu"},
      "2s": {"english": "you(s.) speak", "lithuanian": "tu kalbi"},
      "3s-m": {"english": "he speaks", "lithuanian": "jis kalba"},
      "3s-f": {"english": "she speaks", "lithuanian": "ji kalba"},
      "1p": {"english": "we speak", "lithuanian": "mes kalbame"},
      "2p": {"english": "you(pl.) speak", "lithuanian": "jūs kalbate"},
      "3p-m": {"english": "they(m.) speak", "lithuanian": "jie kalba"},
      "3p-f": {"english": "they(f.) speak", "lithuanian": "jos kalba"}
    },
    "past_tense": {
      "1s": {"english": "I spoke", "lithuanian": "aš kalbėjau"},
      "2s": {"english": "you(s.) spoke", "lithuanian": "tu kalbėjai"},
      "3s-m": {"english": "he spoke", "lithuanian": "jis kalbėjo"},
      "3s-f": {"english": "she spoke", "lithuanian": "ji kalbėjo"},
      "1p": {"english": "we spoke", "lithuanian": "mes kalbėjome"},
      "2p": {"english": "you(pl.) spoke", "lithuanian": "jūs kalbėjote"},
      "3p-m": {"english": "they(m.) spoke", "lithuanian": "jie kalbėjo"},
      "3p-f": {"english": "they(f.) spoke", "lithuanian": "jos kalbėjo"}
    },
    "future": {
      "1s": {"english": "I will speak", "lithuanian": "aš kalbėsiu"},
      "2s": {"english": "you(s.) will speak", "lithuanian": "tu kalbėsi"},
      "3s-m": {"english": "he will speak", "lithuanian": "jis kalbės"},
      "3s-f": {"english": "she will speak", "lithuanian": "ji kalbės"},
      "1p": {"english": "we will speak", "lithuanian": "mes kalbėsime"},
      "2p": {"english": "you(pl.) will speak", "lithuanian": "jūs kalbėsite"},
      "3p-m": {"english": "they(m.) will speak", "lithuanian": "jie kalbės"},
      "3p-f": {"english": "they(f.) will speak", "lithuanian": "jos kalbės"}
    }
  },
  
  "žinoti": {
    "english": "to know",
    "present_tense": {
      "1s": {"english": "I know", "lithuanian": "aš žinau"},
      "2s": {"english": "you(s.) know", "lithuanian": "tu žinai"},
      "3s-m": {"english": "he knows", "lithuanian": "jis žino"},
      "3s-f": {"english": "she knows", "lithuanian": "ji žino"},
      "1p": {"english": "we know", "lithuanian": "mes žinome"},
      "2p": {"english": "you(pl.) know", "lithuanian": "jūs žinote"},
      "3p-m": {"english": "they(m.) know", "lithuanian": "jie žino"},
      "3p-f": {"english": "they(f.) know", "lithuanian": "jos žino"}
    },
    "past_tense": {
      "1s": {"english": "I knew", "lithuanian": "aš žinojau"},
      "2s": {"english": "you(s.) knew", "lithuanian": "tu žinojai"},
      "3s-m": {"english": "he knew", "lithuanian": "jis žinojo"},
      "3s-f": {"english": "she knew", "lithuanian": "ji žinojo"},
      "1p": {"english": "we knew", "lithuanian": "mes žinojome"},
      "2p": {"english": "you(pl.) knew", "lithuanian": "jūs žinojote"},
      "3p-m": {"english": "they(m.) knew", "lithuanian": "jie žinojo"},
      "3p-f": {"english": "they(f.) knew", "lithuanian": "jos žinojo"}
    },
    "future": {
      "1s": {"english": "I will know", "lithuanian": "aš žinosiu"},
      "2s": {"english": "you(s.) will know", "lithuanian": "tu žinosi"},
      "3s-m": {"english": "he will know", "lithuanian": "jis žinos"},
      "3s-f": {"english": "she will know", "lithuanian": "ji žinos"},
      "1p": {"english": "we will know", "lithuanian": "mes žinosime"},
      "2p": {"english": "you(pl.) will know", "lithuanian": "jūs žinosite"},
      "3p-m": {"english": "they(m.) will know", "lithuanian": "jie žinos"},
      "3p-f": {"english": "they(f.) will know", "lithuanian": "jos žinos"}
    }
  },
  
  "galėti": {
    "english": "to be able/can",
    "present_tense": {
      "1s": {"english": "I can", "lithuanian": "aš galiu"},
      "2s": {"english": "you(s.) can", "lithuanian": "tu gali"},
      "3s-m": {"english": "he can", "lithuanian": "jis gali"},
      "3s-f": {"english": "she can", "lithuanian": "ji gali"},
      "1p": {"english": "we can", "lithuanian": "mes galime"},
      "2p": {"english": "you(pl.) can", "lithuanian": "jūs galite"},
      "3p-m": {"english": "they(m.) can", "lithuanian": "jie gali"},
      "3p-f": {"english": "they(f.) can", "lithuanian": "jos gali"}
    },
    "past_tense": {
      "1s": {"english": "I could", "lithuanian": "aš galėjau"},
      "2s": {"english": "you(s.) could", "lithuanian": "tu galėjai"},
      "3s-m": {"english": "he could", "lithuanian": "jis galėjo"},
      "3s-f": {"english": "she could", "lithuanian": "ji galėjo"},
      "1p": {"english": "we could", "lithuanian": "mes galėjome"},
      "2p": {"english": "you(pl.) could", "lithuanian": "jūs galėjote"},
      "3p-m": {"english": "they(m.) could", "lithuanian": "jie galėjo"},
      "3p-f": {"english": "they(f.) could", "lithuanian": "jos galėjo"}
    },
    "future": {
      "1s": {"english": "I will be able", "lithuanian": "aš galėsiu"},
      "2s": {"english": "you(s.) will be able", "lithuanian": "tu galėsi"},
      "3s-m": {"english": "he will be able", "lithuanian": "jis galės"},
      "3s-f": {"english": "she will be able", "lithuanian": "ji galės"},
      "1p": {"english": "we will be able", "lithuanian": "mes galėsime"},
      "2p": {"english": "you(pl.) will be able", "lithuanian": "jūs galėsite"},
      "3p-m": {"english": "they(m.) will be able", "lithuanian": "jie galės"},
      "3p-f": {"english": "they(f.) will be able", "lithuanian": "jos galės"}
    }
  },
  
  "norėti": {
    "english": "to want",
    "present_tense": {
      "1s": {"english": "I want", "lithuanian": "aš noriu"},
      "2s": {"english": "you(s.) want", "lithuanian": "tu nori"},
      "3s-m": {"english": "he wants", "lithuanian": "jis nori"},
      "3s-f": {"english": "she wants", "lithuanian": "ji nori"},
      "1p": {"english": "we want", "lithuanian": "mes norime"},
      "2p": {"english": "you(pl.) want", "lithuanian": "jūs norite"},
      "3p-m": {"english": "they(m.) want", "lithuanian": "jie nori"},
      "3p-f": {"english": "they(f.) want", "lithuanian": "jos nori"}
    },
    "past_tense": {
      "1s": {"english": "I wanted", "lithuanian": "aš norėjau"},
      "2s": {"english": "you(s.) wanted", "lithuanian": "tu norėjai"},
      "3s-m": {"english": "he wanted", "lithuanian": "jis norėjo"},
      "3s-f": {"english": "she wanted", "lithuanian": "ji norėjo"},
      "1p": {"english": "we wanted", "lithuanian": "mes norėjome"},
      "2p": {"english": "you(pl.) wanted", "lithuanian": "jūs norėjote"},
      "3p-m": {"english": "they(m.) wanted", "lithuanian": "jie norėjo"},
      "3p-f": {"english": "they(f.) wanted", "lithuanian": "jos norėjo"}
    },
    "future": {
      "1s": {"english": "I will want", "lithuanian": "aš norėsiu"},
      "2s": {"english": "you(s.) will want", "lithuanian": "tu norėsi"},
      "3s-m": {"english": "he will want", "lithuanian": "jis norės"},
      "3s-f": {"english": "she will want", "lithuanian": "ji norės"},
      "1p": {"english": "we will want", "lithuanian": "mes norėsime"},
      "2p": {"english": "you(pl.) will want", "lithuanian": "jūs norėsite"},
      "3p-m": {"english": "they(m.) will want", "lithuanian": "jie norės"},
      "3p-f": {"english": "they(f.) will want", "lithuanian": "jos norės"}
    }
  },
  
  "matyti": {
    "english": "to see",
    "present_tense": {
      "1s": {"english": "I see", "lithuanian": "aš matau"},
      "2s": {"english": "you(s.) see", "lithuanian": "tu matai"},
      "3s-m": {"english": "he sees", "lithuanian": "jis mato"},
      "3s-f": {"english": "she sees", "lithuanian": "ji mato"},
      "1p": {"english": "we see", "lithuanian": "mes matome"},
      "2p": {"english": "you(pl.) see", "lithuanian": "jūs matote"},
      "3p-m": {"english": "they(m.) see", "lithuanian": "jie mato"},
      "3p-f": {"english": "they(f.) see", "lithuanian": "jos mato"}
    },
    "past_tense": {
      "1s": {"english": "I saw", "lithuanian": "aš mačiau"},
      "2s": {"english": "you(s.) saw", "lithuanian": "tu matei"},
      "3s-m": {"english": "he saw", "lithuanian": "jis matė"},
      "3s-f": {"english": "she saw", "lithuanian": "ji matė"},
      "1p": {"english": "we saw", "lithuanian": "mes matėme"},
      "2p": {"english": "you(pl.) saw", "lithuanian": "jūs matėte"},
      "3p-m": {"english": "they(m.) saw", "lithuanian": "jie matė"},
      "3p-f": {"english": "they(f.) saw", "lithuanian": "jos matė"}
    },
    "future": {
      "1s": {"english": "I will see", "lithuanian": "aš matysiu"},
      "2s": {"english": "you(s.) will see", "lithuanian": "tu matysi"},
      "3s-m": {"english": "he will see", "lithuanian": "jis matys"},
      "3s-f": {"english": "she will see", "lithuanian": "ji matys"},
      "1p": {"english": "we will see", "lithuanian": "mes matysime"},
      "2p": {"english": "you(pl.) will see", "lithuanian": "jūs matysite"},
      "3p-m": {"english": "they(m.) will see", "lithuanian": "jie matys"},
      "3p-f": {"english": "they(f.) will see", "lithuanian": "jos matys"}
    }
  },
}

# Helper functions to work with the new verb structure

def get_all_verbs():
    """
    Get a list of all verb infinitives.
    
    Returns:
        list: List of verb infinitives
    """
    return list(verbs_new.keys())

def get_verb_conjugations(verb_infinitive):
    """
    Get all conjugations for a specific verb.
    
    Args:
        verb_infinitive (str): The infinitive form of the verb
        
    Returns:
        dict: Conjugation data for the verb, or None if not found
    """
    return verbs_new.get(verb_infinitive)

def get_all_conjugation_forms():
    """
    Get all conjugation forms in a flat list (for backward compatibility).
    
    Returns:
        list: List of all conjugation forms with corpus and group info
    """
    flat_forms = []
    
    for infinitive, verb_data in verbs_new.items():
        for tense_name, tense_forms in verb_data.items():
            if tense_name == "english":  # Skip the English translation
                continue
                
            for person_key, form_data in tense_forms.items():
                flat_form = form_data.copy()
                flat_form['infinitive'] = infinitive
                flat_form['tense'] = tense_name
                flat_form['person'] = person_key
                flat_form['corpus'] = 'verbs'
                flat_form['group'] = f"{infinitive}_{tense_name}"
                flat_forms.append(flat_form)
    
    return flat_forms

def get_conjugations_by_tense(tense):
    """
    Get all conjugations for a specific tense organized by verb categories.
    
    Args:
        tense (str): The tense ('present_tense', 'past_tense', 'future')
        
    Returns:
        dict: Dictionary with verb categories as keys and lists of conjugation forms as values
    """
    # Define verb categories
    verb_categories = {
      "Movement & Travel": [
        "eiti",      # to walk/go
        "bėgti",     # to run
        "ateiti",    # to come
        "grįžti",    # to return
        "važiuoti",  # to drive/travel
        "vykti"      # to go/proceed
      ],
      
      "Basic Needs & Daily Life": [
        "valgyti",   # to eat
        "gerti",     # to drink
        "miegoti",   # to sleep
        "gyventi",   # to live
        "dirbti",    # to work
        "žaisti"     # to play
      ],
      
      "Mental & Emotional": [
        "mėgti",     # to like
        "žinoti",    # to know
        "norėti",    # to want
        "galėti",    # to be able/can
      ],
      
      "Sensory Perception": [
        "matyti",    # to see
        "kalbėti",   # to speak
        "klausyti",  # to listen
      ],

      "Learning & Knowledge": [
        "skaityti",  # to read
        "rašyti",    # to write
        "mokyti",    # to teach
        "mokytis",   # to learn
      ],
      
      "Actions & Transactions": [
        "būti",      # to be
        "turėti",    # to have
        "pirkti",    # to buy
        "duoti",     # to give
        "imti",      # to take
        "gaminti"    # to make/produce
      ]
    }
    
    result = {}
    
    for category, verb_list in verb_categories.items():
        result[category] = []
        
        for infinitive in verb_list:
            if infinitive in verbs_new and tense in verbs_new[infinitive]:
                # Add all conjugation forms for this verb in the specified tense
                for person_key, form_data in verbs_new[infinitive][tense].items():
                    result[category].append({
                        "english": form_data["english"],
                        "lithuanian": form_data["lithuanian"],
                        "person": person_key
                    })
    
    return result


verbs_present = get_conjugations_by_tense('present_tense')
verbs_past = get_conjugations_by_tense('past_tense')
verbs_future = get_conjugations_by_tense('future')
