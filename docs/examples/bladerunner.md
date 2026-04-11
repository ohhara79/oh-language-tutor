# Example session: Blade Runner

A real transcript of `oh-language-tutor` running against Blade Runner
(ScummVM) in the opening scene at Howie Lee's noodle bar, where McCoy
tries to question Gordo Frizz and Zuben.

## Pipeline

```sh
scummvm 2>&1 \
  | uv run --frozen --no-dev main.py \
      --source-language English \
      --target-language Korean \
      --level intermediate \
      --extra-system-prompt extras/bladerunner.md \
      --filter-regex '^\w+: "'
```

Speaker ids come from the Blade Runner cast table in
`extras/bladerunner.md` (`0` = McCoy, `2` = Gordo Frizz, `19` = Zuben,
etc.).

## Transcript

0: "McCoy, LPD. I want to ask you a couple of questions."

── 🎓 0 ─────────────────────────────────────────────────────────────────

🎯 Translation: "맥코이, 경찰입니다. 몇 가지 질문 좀 하겠습니다."

📚 Vocabulary:
- **LPD** → Los Angeles Police Department (LA 경찰국, 작중에서는 LAPD 대신 LPD로 씀)
- **a couple of questions** → 몇 가지 질문

💡 Expression: **"a couple of questions"** — 느와르/형사물에서 거의 공식처럼 쓰이는 표현이에요. 직역하면 "두세 개 질문"이지만, 실제로는 본격적인 심문을 시작하겠다는 뜻입니다. 하드보일드 형사가 이렇게 말하면 상대방은 긴장해야 해요 😅 한국 형사 드라마의 "잠깐 얘기 좀 합시다"와 비슷한 느낌입니다.

🎬 Context: McCoy가 수사 대상에게 자신의 신분(블레이드 러너/경찰)을 밝히며 심문을 시작하는 전형적인 느와르 오프닝 대사입니다.

────────────────────────────────────────────────────────────────────────

2: "Sorry, my man. I just don't got the time."

── 🎓 2 ─────────────────────────────────────────────────────────────────

🎯 Translation: "미안하지만, 친구. 시간이 없어서."

📚 Vocabulary:
- **my man** → 친구, 형씨 (친근하면서도 거리를 두는 호칭)
- **don't got the time** → 시간이 없다

💡 Expression: **"don't got the time"** — 문법적으로는 "don't have the time"이 맞지만, 구어체/슬랭에서는 **"don't got"**을 자주 씁니다. 특히 거리의 인물들이 이런 비표준 문법을 쓰면 "나는 교양 있는 사람이 아니고, 너한테 협조할 의무도 못 느낀다"는 태도가 묻어나요. 느와르에서 경찰의 질문을 이렇게 가볍게 튕겨내는 건 전형적인 **비협조적 목격자/용의자** 패턴입니다.

🎬 Context: McCoy가 경찰 신분을 밝히며 질문하겠다고 했는데, Gordo Frizz가 "시간 없다"며 쿨하게 거절하는 장면입니다. 블레이드 러너 앞에서도 태연한 걸 보면, 뭔가 숨기고 있거나 정말 신경 쓸 겨를이 없거나 둘 중 하나겠죠.

────────────────────────────────────────────────────────────────────────

19: "Got to mix more out back."

── 🎓 19 ────────────────────────────────────────────────────────────────

🎯 Translation: "뒤쪽에서 더 섞어야 해서." (재료를 더 조합해야 한다는 뜻)

📚 Vocabulary:
- **mix** → 섞다, 조합하다
- **out back** → 뒤쪽에서, 가게 뒷편에서

💡 Expression: **"Got to ~"** — "I've got to ~" 또는 "I have to ~"의 구어체 축약형입니다. 주어 "I"를 아예 생략하는 건 일상 회화에서 매우 흔해요. "Got to go" (가야 해), "Got to run" (빨리 가야 해) 같은 식으로 자주 씁니다. 여기서도 Zuben이 바쁜 척하면서 McCoy를 피하려는 느낌이 강합니다.

🎬 Context: McCoy가 질문하려 하자 앞서 Gordo Frizz도 시간 없다며 거절했는데, 이번엔 Zuben도 "뒤에서 할 일이 있다"며 자리를 피하려 합니다. 두 사람 연달아 비협조적이면… 수상하죠. 🕵️

────────────────────────────────────────────────────────────────────────

0: "You're a pretty smart looking cat."

── 🎓 0 ─────────────────────────────────────────────────────────────────

🎯 Translation: "넌 꽤 똑똑해 보이는 녀석이잖아."

📚 Vocabulary:
- **cat** → 녀석, 친구 (슬랭으로 '사람'을 뜻함)
- **pretty** → 꽤, 상당히 (여기서는 "예쁜"이 아님!)
- **smart looking** → 똑똑해 보이는, 영리해 보이는

💡 Expression: **"cat"** — 1940~50년대 재즈/비트닉 문화에서 유래한 슬랭으로 "남자, 녀석"을 뜻합니다. 느와르 형사물에서 자주 등장하는 표현이에요. "cool cat" (멋진 녀석), "hip cat" (센스 있는 녀석) 같은 조합도 있습니다. 현대 영어에서는 거의 안 쓰지만, 블레이드 러너의 레트로-느와르 분위기에 딱 맞는 단어죠.

🎬 Context: Zuben이 "뒤에서 일해야 한다"며 피하려 하자, McCoy가 은근히 압박하는 대사입니다. "넌 머리 좋은 녀석이니까 내 말 알아듣겠지?" — 하드보일드 형사 특유의 **칭찬인 척 하는 위협**이에요. 부드럽게 말하지만 속뜻은 "도망치지 말고 협조해"입니다.

────────────────────────────────────────────────────────────────────────

0: "Wanna make some money?"

── 🎓 0 ─────────────────────────────────────────────────────────────────

🎯 Translation: "돈 좀 벌고 싶어?"

📚 Vocabulary:
- **wanna** → want to의 구어체 축약형
- **make money** → 돈을 벌다

💡 Expression: **"Wanna make some money?"** — 느와르 형사의 전형적인 **정보 매수 전략**입니다. 질문에 협조하면 돈을 주겠다는 뜻이죠. 한국 형사 드라마에서 "이거 하나만 알려줘, 내가 손해 안 보게 해줄게"와 비슷한 뉘앙스예요. 아까 칭찬("smart looking cat")으로 분위기를 띄워놓고, 바로 돈을 제시하는 게 **당근(carrot)** 작전의 정석입니다.

🎬 Context: Gordo Frizz와 Zuben 모두 McCoy의 질문을 피하려 했죠. McCoy는 이제 전략을 바꿔서 — 위협 대신 **돈으로 회유**하려 합니다. 똑똑한 녀석이라고 추켜세운 다음 바로 돈 얘기를 꺼내는, 노련한 형사의 수법입니다. 🕵️💰

────────────────────────────────────────────────────────────────────────

2: "Pay me large, you got my rapt attention."

── 🎓 2 ─────────────────────────────────────────────────────────────────

🎯 Translation: "크게 쏘면, 온 신경 집중해서 들어줄게."

📚 Vocabulary:
- **pay me large** → 크게 쏘다, 돈을 많이 주다
- **rapt attention** → 완전히 집중한 관심, 몰입한 주의

💡 Expression: **"rapt attention"** — "rapt"는 "완전히 빠져든, 몰입한"이라는 뜻의 형용사예요. 보통 "pay rapt attention" (열중해서 듣다)이라는 표현으로 씁니다. 여기서 Gordo Frizz가 재치 있는 게, McCoy가 "**pay** me"(돈을 내라)와 "**pay** attention"(주의를 기울이다)의 **pay를 이중으로** 활용하고 있다는 점이에요. "돈을 내면(pay) → 주의를 기울여 주겠다(pay attention)" — 말장난(wordplay)입니다.

🎬 Context: 아까 "시간 없다(don't got the time)"며 쿨하게 거절했던 Gordo Frizz가, McCoy가 돈 얘기를 꺼내자 태도가 180도 바뀌었습니다. 😄 결국 돈이면 다 되는 거리의 인물이라는 걸 보여주는, 느와르다운 장면이죠.

────────────────────────────────────────────────────────────────────────

0: "Depends on how much the information is worth."

── 🎓 0 ─────────────────────────────────────────────────────────────────

🎯 Translation: "그건 정보가 얼마나 가치 있느냐에 달렸지."

📚 Vocabulary:
- **depends on** → ~에 달려 있다, ~에 따라 다르다
- **worth** → 가치가 있는 (be worth ~)

💡 Expression: **"Depends on ~"** — 주어 "It"을 생략한 구어체입니다. 원래는 "It depends on ~"이죠. 느와르 형사들은 절대 먼저 가격을 부르지 않아요. **"네가 뭘 줄 수 있느냐에 따라 내가 뭘 줄지 정한다"** — 이게 하드보일드 협상의 기본입니다. 주도권을 상대에게 넘기지 않는 거죠.

🎬 Context: Gordo Frizz가 "크게 쏘라"며 욕심을 부리자, McCoy는 바로 선불은 없다는 식으로 견제합니다. "좋은 정보를 주면 그만큼 주겠다"는 조건부 제안이에요. 돈을 미끼로 던져놓고도 쉽게 지갑을 열지 않는 — McCoy의 노련한 협상 스타일이 드러나는 대사입니다. 🕵️

────────────────────────────────────────────────────────────────────────

2: "Unfortunately, my man, I got to book."

── 🎓 2 ─────────────────────────────────────────────────────────────────

🎯 Translation: "안됐지만, 친구. 나 빠져야겠어."

📚 Vocabulary:
- **unfortunately** → 안타깝게도, 유감이지만
- **book** → (슬랭) 급히 떠나다, 튀다

💡 Expression: **"got to book"** — "book"이 여기서는 "책"이 아니라 **"급히 자리를 뜨다, 튀다"**라는 슬랭이에요! "I gotta bounce", "I gotta split", "I gotta jet"과 같은 뜻입니다. 원래 "book it"에서 온 표현으로, 미국 구어체에서 꽤 자주 쓰입니다. 한국어의 "나 빠진다", "나 튄다"와 딱 맞는 느낌이에요.

🎬 Context: McCoy가 "정보 가치에 따라 돈을 주겠다"며 공짜 선불은 없다고 견제하자, Gordo Frizz가 다시 비협조 모드로 돌아갑니다. 아까도 "시간 없다(don't got the time)"고 했고, 지금도 "가야 한다(got to book)"며 피하네요. 돈을 크게 안 줄 거면 관심 없다는 태도 — 거리의 정보상다운 행동이죠. 😏

────────────────────────────────────────────────────────────────────────

2: "Dynamite dinin', old man."

── 🎓 2 ─────────────────────────────────────────────────────────────────

🎯 Translation: "끝내주는 식사 되세요, 영감님."

📚 Vocabulary:
- **dynamite** → (슬랭) 끝내주는, 대단한, 폭발적인
- **dinin'** → dining(식사)의 구어체 발음 (g 탈락)

💡 Expression: **"dynamite"** — 원래 "다이너마이트(폭약)"이지만, 슬랭으로는 **"최고의, 굉장한"**이라는 뜻이에요. "That movie was dynamite!" (그 영화 끝내줬어!) 같은 식으로 씁니다. 비슷한 슬랭으로 "killer", "bomb", "fire" 등이 있어요 — 영어에서는 위험하고 강렬한 것들이 "좋다"는 뜻으로 쓰이는 패턴이 재밌죠! 💣

🎬 Context: Gordo Frizz가 떠나면서 McCoy에게 던지는 비꼬는 인사입니다. "old man(영감님)"이라는 호칭도 살짝 도발적이에요. 정보를 돈 주고 사려 했지만 가격 협상이 안 맞으니, 빈정거리면서 "맛있게 드세요~" 하고 유유히 사라지는 거죠. McCoy 입장에서는 꽤 짜증나는 상황입니다. 😤

────────────────────────────────────────────────────────────────────────

2: "Catch you later."

── 🎓 2 ─────────────────────────────────────────────────────────────────

🎯 Translation: "나중에 보자."

📚 Vocabulary:
- **catch you later** → 나중에 보자, 다음에 봐

💡 Expression: **"Catch you later"** — 캐주얼한 작별 인사로 "See you later"와 같은 뜻이에요. 하지만 느와르 맥락에서 **"catch"**라는 단어가 의미심장합니다. "catch"에는 "잡다, 체포하다"라는 뜻도 있으니까요. 블레이드 러너(레플리컨트 사냥꾼) 앞에서 "나중에 잡아봐~"라고 하는 것처럼 들릴 수도 있는, 이중적인 뉘앙스가 있어요.

🎬 Context: Gordo Frizz의 퇴장 마무리입니다. "끝내주는 식사 되세요, 영감님" 다음에 "나중에 보자"까지 — 경찰 질문을 완전히 무시하고 여유롭게 사라지네요. McCoy가 돈으로 회유하려 했지만 결국 실패한 셈입니다. 이제 남은 건 Zuben뿐이죠. 🕵️

────────────────────────────────────────────────────────────────────────
