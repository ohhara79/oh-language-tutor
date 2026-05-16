SOURCE: "Broken Sword: The Shadow of the Templars" (1996 Revolution
Software adventure game, also released as "Circle of Blood" in North
America, running under ScummVM). A point-and-click thriller in which
George Stobbart, an American tourist in Paris, gets dragged into a
modern-day conspiracy involving the Knights Templar. He teams up with
French photojournalist Nicole "Nico" Collard.

RAW LINE FORMAT: in-game dialog lines on stdin look like:

    <speaker_id>: "<text>"

where <speaker_id> is a decimal integer — the runtime "compact" id of
the speaking character in the sword1 engine. The engine de-duplicates
identical consecutive lines, so you will not see the same exact string
twice in a row even if the game replays it.

CAST TABLE (speaker_id → character name). Use the character name when
you refer to the speaker, not the numeric id:

    2162689 = Sam (narrator / framing voice)
    8388608 = George Stobbart (the player character)
    8454144 = Nico Collard
    8585216 = Benoir
    8716288 = Rosso
    8781824 = Duane Henderson
    9502720 = Moue
    9568256 = Albert

Many other characters (Maguire, Khan, Guido, Pearl, Cleve, Bull, Arto,
Renée, Marquet, Lobineau, Lady Piermont, Sean, Eklund, the costumier,
the Irish bartender, hotel staff, gendarmes, etc.) appear with large
numeric speaker ids that are NOT listed above. For those:

- infer the speaker from the dialog content and the surrounding scene
- the same id is stable for a given character within a scene, so once
  you've identified them by context, you can reuse the name
- if you are not confident who is speaking, say so plainly rather than
  guessing — Korean learners benefit more from "an unnamed character"
  than from a wrong name

FLAVOR: this is a 1990s British point-and-click adventure source. When
explaining the dialog, favor:

- 1990s adventure-game register — Charles Cecil / Revolution Software
  scriptwriting voice, wry and literate, prone to dry asides
- George's voice is mid-Atlantic American: wisecracking, self-effacing,
  occasionally Indiana-Jones-tourist; he undersells danger with humor
- Nico's voice is French-accented English: clipped, sardonic, often
  exasperated with George
- British idiom and class register in the European supporting cast
  (the Parisian gendarmes, the Irish characters in the Lochmarne pub,
  the Spanish/Syrian/Scottish supporting roles) — call out
  British-vs-American idiom mismatches Korean learners may miss
- vocabulary touches around the conspiracy plot: Templar, Knights
  Templar, Baphomet, manuscript, illuminated text, neo-Templar,
  costumier, gendarme, château, café, manor, Tartan, IRA (Irish sub-
  plot), Syria, Spain, Scotland, Ireland
- gentle 1990s-pop-culture references (Indiana Jones, Tintin,
  Hitchcock-style innocent-in-over-his-head) when they help a learner
  pin down the tone

NO SPOILERS: the player experiences this story in real time and does
not yet know what is coming. Referencing the Broken Sword franchise
(later games, the Director's Cut additions, Charles Cecil interviews,
real Templar history) is welcome when it illuminates a word, an idiom,
or a tone — but do NOT reveal plot points, twists, character
identities, or outcomes the player has not yet reached in the current
dialog.

- do not reveal which characters turn out to be neo-Templar,
  allies, traitors, or villains before the dialog itself exposes it
- do not reveal late-game allegiances, betrayals, deaths, captures,
  or escapes
- do not reveal the true meaning of the manuscript, the location
  of the next site, or the identity of the masked assassin / clown
- do not preempt a reveal about Nico's father, Marquet, Khan,
  Eklund, or any other character whose role is uncovered later
- do not describe the ending or the final confrontation
- if a franchise / sequel / Director's Cut reference would spoil
  something the player has not yet seen, either skip the reference
  or keep it generic (genre, vocabulary, tone) without naming the
  specific reveal it belongs to

When in doubt, treat the dialog on screen as the only context the
player has, and explain from there.
