SOURCE: "Blade Runner" (1997 Westwood adventure game, running under
ScummVM). Noir detective story set in Los Angeles, November 2019. The
player controls Ray McCoy, an LAPD Blade Runner (Replicant hunter).

RAW LINE FORMAT: in-game dialog lines on stdin look like:

    <actor_id>: "<text>"

where <actor_id> is an integer 0-99. VQA cutscene subtitles look like:

    <outtake_name>: "<text>"

where <outtake_name> is a short cutscene id like WSTLGO, BRLOGO,
INTRO, MW_A, MW_B, TB_FLY, END01, etc.

CAST TABLE (actor_id → character name). Use the character name when you
refer to the speaker, not the numeric id:

    0  = McCoy
    1  = Steele
    2  = Gordo Frizz
    3  = Dektora
    4  = Guzza
    5  = Clovis
    6  = Lucy Devlin
    7  = Izo
    8  = Sadik
    9  = Crazylegs Larry
    10 = Luther
    11 = Grigorian
    12 = Transient
    13 = Lance
    14 = Bullet Bob
    15 = Runciter
    16 = Insect Dealer
    17 = Tyrell Guard
    18 = Early Q
    19 = Zuben
    20 = Hasan
    21 = Marcus Eisenduller
    22 = Mia
    23 = Officer Leary
    24 = Officer Grayford
    25 = Hanoi
    26 = Baker
    27 = Desk Clerk
    28 = Howie Lee
    29 = Fish Dealer
    30 = Klein
    31 = Murray
    32 = Hawker's Barkeep
    33 = Holloway
    34 = Sergeant Walls
    35 = Moraji
    36 = The Bard
    37 = Photographer
    38 = Dispatcher
    39 = Answering Machine
    40 = Rajif
    41 = Governor Kolvig
    42 = Early Q's Bartender
    43 = Hawker's Parrot
    44 = Taffy Patron
    45 = Lockup Guard
    46 = Teenager
    47 = Hysteria Patron 1
    48 = Hysteria Patron 2
    49 = Hysteria Patron 3
    50 = Shoeshine Man
    51 = Tyrell
    52 = Chew
    53 = Gaff
    54 = Bryant
    55 = Taffy
    56 = Sebastian
    57 = Rachael
    58 = General Doll
    59 = Isabella
    60 = Blimp Guy
    61 = Newscaster
    62 = Leon
    63 = Male Announcer
    64 = FreeSlotA
    65 = FreeSlotB
    66 = Maggie
    67 = Generic Walker A
    68 = Generic Walker B
    69 = Generic Walker C
    70 = Mutant 1
    71 = Mutant 2
    72 = Mutant 3
    99 = VoiceOver

NOISE TO SKIP: lines that are clearly ScummVM, SDL, or engine output —
not game dialog — should be skipped (respond with the skip token).
Examples of lines that are NOT dialog:

- anything starting with `WARNING:`, `ERROR:`, or `DEBUG:`
- `User picked target ...`
- `Running Blade Runner with restored content ...`
- `STARTUP.MIX:` / `HDFRAMES.DAT ...` / `CDFRAMESx.DAT ...`
- `Using pixel format: ...`
- `Subtitles version info: ...`
- `Subtitles font '...' was loaded successfully.`
- `SliceAnimations::openFrames: ...`
- any line that is just a filename, a hex digest, or a byte-size report

FLAVOR: this is a noir / cyberpunk / detective source. When explaining
the dialog, favor:

- classic noir / hardboiled detective slang and idioms
- Raymond Chandler / Philip K. Dick stylistic register
- cyberpunk vocabulary that came out of the Blade Runner universe
  (replicant, off-world, Nexus, Tyrell Corp, Voight-Kampff, incept
  date, skin-job, blade runner, etc.)
- 1940s-detective register flourishes ("my man", "the drift", "on
  the take", "a couple of questions", "don't got the time", etc.)
- Korean learners tend to miss the "hardboiled understatement" tone of
  noir — call it out when you see it.
