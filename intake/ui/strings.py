"""UI chrome strings (buttons, headings) in en/hi/mr. Hindi/Marathi are machine-drafted, needs native review."""
S = {
    "title": ("Patient intake", "मरीज़ की जानकारी", "रुग्ण माहिती"),
    "language": ("Language", "भाषा", "भाषा"),
    "back": ("← Back", "← पीछे", "← मागे"),
    "skip": ("Skip", "छोड़ें", "वगळा"),
    "unsure": ("Not sure", "पक्का नहीं", "खात्री नाही"),
    "next": ("Next →", "आगे →", "पुढे →"),
    "type_here": ("Type here", "यहाँ लिखें", "येथे लिहा"),
    "review": ("Please check your answers", "कृपया अपने जवाब जाँचें", "कृपया तुमची उत्तरे तपासा"),
    "change": ("Change", "बदलें", "बदला"),
    "confirm": ("Everything is correct - finish", "सब सही है - पूरा करें", "सर्व बरोबर आहे - पूर्ण करा"),
    "done": ("Thank you. Please wait for the staff to call you.", "धन्यवाद। कृपया स्टाफ के बुलाने तक प्रतीक्षा करें।", "धन्यवाद. कृपया कर्मचाऱ्यांनी बोलावेपर्यंत थांबा."),
    "declined": ("No problem. No questions were asked and nothing was saved. Please speak to the staff.",
                 "कोई बात नहीं। कोई सवाल नहीं पूछा गया और कुछ सहेजा नहीं गया। कृपया स्टाफ से बात करें।",
                 "ठीक आहे. कोणताही प्रश्न विचारला नाही आणि काहीही जतन केले नाही. कृपया कर्मचाऱ्यांशी बोला."),
    "new": ("Start for next patient", "अगले मरीज़ के लिए शुरू करें", "पुढील रुग्णासाठी सुरू करा"),
    "progress": ("Question", "सवाल", "प्रश्न"),
    "pick_many": ("Tap all that apply, then press Next.", "जो लागू हों सब चुनें, फिर आगे दबाएँ।", "जे लागू असेल ते सर्व निवडा, मग पुढे दाबा."),
    "bm_list": ("Choose from a list instead", "इसके बजाय सूची से चुनें", "त्याऐवजी यादीतून निवडा"),
    "bm_clear": ("Clear", "हटाएँ", "पुसा"),
    "bm_none_selected": ("Tap the body, or use the list below.", "शरीर पर दबाएँ, या नीचे की सूची से चुनें।", "शरीरावर दाबा, किंवा खालील यादी वापरा."),
}


def t(key: str, lang: str) -> str:
    return S[key][{"en": 0, "hi": 1, "mr": 2}.get(lang, 0)]
