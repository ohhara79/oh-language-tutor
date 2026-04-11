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

    0  = McCoy               (the player, an LAPD Blade Runner)
    1  = Steele              (veteran Blade Runner, McCoy's rival)
    2  = Gordo Frizz         (stand-up comedian, possible Replicant)
    3  = Dektora              (exotic dancer, possible Replicant)
    4  = Guzza               (McCoy's corrupt LAPD boss)
    5  = Clovis              (Replicant leader)
    6  = Lucy Devlin          (missing teenager)
    7  = Izo                 (Japanese weapons dealer, ex-activist)
    8  = Sadik               (brutal Replicant enforcer)
    9  = Crazylegs Larry      (car dealer)
    10 = Luther              (Replicant twin, tech specialist)
    11 = Grigorian            (Replicant rights activist)
    12 = Transient            (homeless man)
    13 = Lance               (Luther's Replicant twin)
    14 = Bullet Bob           (gun shop owner)
    15 = Runciter             (pet shop owner)
    16 = Insect Dealer
    17 = Tyrell Guard
    18 = Early Q              (nightclub owner)
    19 = Zuben                (Replicant short-order cook)
    20 = Hasan                (fish market dealer)
    21 = Marcus Eisenduller   (murdered scientist)
    22 = Mia                  (Grigorian's assistant)
    23 = Officer Leary        (beat cop)
    24 = Officer Grayford     (beat cop)
    25 = Hanoi                (Early Q's bouncer)
    26 = Baker
    27 = Desk Clerk
    28 = Howie Lee            (sushi-bar owner)
    29 = Fish Dealer
    30 = Klein                (LAPD lab tech)
    31 = Murray               (pawn shop owner)
    32 = Hawker's Barkeep
    33 = Holloway             (Replicant hunter)
    34 = Sergeant Walls       (LAPD desk sergeant)
    35 = Moraji               (scientist)
    36 = The Bard
    37 = Photographer
    38 = Dispatcher           (police radio dispatcher)
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
    51 = Tyrell               (Replicant creator)
    52 = Chew                 (eye designer)
    53 = Gaff                 (LAPD Blade Runner, cryptic)
    54 = Bryant               (LAPD captain)
    55 = Taffy                (nightclub owner)
    56 = Sebastian            (Tyrell's genetic designer)
    57 = Rachael              (experimental Replicant)
    58 = General Doll
    59 = Isabella
    60 = Blimp Guy            (flying-billboard PA)
    61 = Newscaster
    62 = Leon                 (Replicant)
    63 = Male Announcer
    64 = FreeSlotA            (usually a rat)
    65 = FreeSlotB            (usually a rat)
    66 = Maggie               (McCoy's dog)
    67 = Generic Walker A
    68 = Generic Walker B
    69 = Generic Walker C
    70 = Mutant 1
    71 = Mutant 2
    72 = Mutant 3
    99 = VoiceOver            (McCoy's internal monologue / narrator)

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
