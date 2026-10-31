# Golden photo set results

50 openly licensed Wikimedia Commons product photos (sources in photo_sources.csv; fetch_photos.py re-downloads them). Reference codes come from HTS Rev 21. Photo only, no user text, first classification round, live DeepSeek deepseek-flash.

| Metric | Run 1 | Run 2 (heading step, stemmer fix) |
|---|---|---|
| Top choice, correct 4 digit heading (of 50) | 38 | 44 |
| Top choice, correct 6 digit subheading (of 50) | 32 | 41 |
| Correct subheading in top 3 (of 50) | 33 | 43 |
| Top choice, exact 10 digit code | 23 of 39 scorable | 28 of 39 scorable |
| Codes assigned without asking | 1 | 3 |
| Assigned codes correct | 1 | 3 |
| Mean cost per receipt, USD | 0.000354 | 0.000498 |

Outcomes run 2: marginal 39, strong 3, weak 8

## Per photo, run 2

| Item | Identified as | Top code | Expected subheading | Heading | Subheading | Outcome |
|---|---|---|---|---|---|---|
| whisk | Wire whisks (balloon, spiral, and bead s | 8205513030 | 820551 | Y | Y | marginal |
| tshirt | green short-sleeve t-shirt | 6109100004 | 610910 | Y | Y | marginal |
| laptop | laptop computer | 8471300100 | 847130 | Y | Y | strong |
| smartphone | Smartphone | 8517130000 | 851713 | Y | Y | marginal |
| desk_lamp | white pedestal display stand with logo t | 9403704031 | 940521 | n | n | weak |
| mug | Ceramic coffee pot with matching mug | 6912004400 | 691110 or 691200 | Y | Y | marginal |
| vacuum_flask | Vacuum insulated beverage flask with cup | 9617001000 | 961700 | Y | Y | marginal |
| office_chair | upholstered armchair on casters | 9401710031 | 940131 or 940139 | Y | n | marginal |
| sneakers | Low-top lace-up sneakers | 6404193980 | 640411 or 640419 | Y | Y | marginal |
| handbag | Green ostrich-textured leather handbag w | 4202213000 | 420221 | Y | Y | marginal |
| backpack | Hiking backpack with trekking poles and  | 4202923120 | 420292 | Y | Y | marginal |
| sunglasses | Sunglasses | 9004100000 | 900410 | Y | Y | marginal |
| headphones | Over-ear headphones | 8518302000 | 851830 | Y | Y | marginal |
| teddy_bear | Stuffed teddy bear | 9503000090 | 950300 | Y | Y | marginal |
| lego | Grey plastic building toy connector piec | 9503000090 | 950300 | Y | Y | marginal |
| bicycle | bicycle | 8712004800 | 871200 | Y | Y | marginal |
| umbrella | Folding umbrella with matching sleeve | 6601910000 | 660191 or 660199 | Y | Y | marginal |
| skillet | Cast iron skillet with baked food | 7323915020 | 732391 | Y | Y | marginal |
| drinking_glass | Engraved clear glass beaker | 7013374000 | 701337 | Y | Y | marginal |
| hammer | Claw hammer | 8205203000 | 820520 | Y | Y | marginal |
| screwdriver | Phillips screwdriver | 8205513060 | 820540 | Y | n | weak |
| scissors | Scissors | 8213009000 | 821300 | Y | Y | marginal |
| drill | Cordless drill/driver | 8467210010 | 846721 | Y | Y | marginal |
| hair_dryer | Handheld electric hair dryer | 8516310000 | 851631 | Y | Y | strong |
| toaster | Electric conveyor toaster oven | 8516720000 | 851672 | Y | Y | weak |
| kettle | Electric cordless kettle | 8516790000 | 851679 | Y | Y | marginal |
| blender | Countertop electric blender with plastic | 8509400015 | 850940 | Y | Y | marginal |
| vacuum_cleaner | Upright vacuum cleaner | 8508190000 | 850811 or 850819 | Y | Y | marginal |
| led_bulb | LED light bulb | 9405426000 | 853952 | n | n | weak |
| fan | Vintage electric desk fan | 8414519090 | 841451 | Y | Y | marginal |
| usb_cable | USB-C cable | 8544429090 | 854442 | Y | Y | weak |
| cutting_board | Round wooden plate or platter | 4419209000 | 441911 or 441920 or 441990 | Y | Y | marginal |
| food_container | Molded plastic arched cover or housing | 3926909940 | 392410 | n | n | weak |
| towel | blue tufted textile fabric | 5802300020 | 630260 | n | n | weak |
| sweater | Knitted pullover sweater | 6110190015 | 611011 | Y | n | marginal |
| wallet | Leather wallet | 4202313000 | 420231 | Y | Y | marginal |
| cap | Baseball cap | 6506996000 | 650500 | n | n | weak |
| socks | Knitted neck scarf | 6117106020 | 611595 | n | n | marginal |
| candle | Burning candle | 3406000000 | 340600 | Y | Y | marginal |
| picture_frame | Picture frame with mat | 4414100000 | 441410 or 441490 | Y | Y | marginal |
| mirror | Ornately carved framed wall mirror | 7009921090 | 700992 | Y | Y | marginal |
| padlock | Padlocks | 8301106080 | 830110 | Y | Y | marginal |
| tennis_racket | Tennis racket with two tennis balls | 9506512000 | 950651 | Y | Y | marginal |
| soccer_ball | Soccer ball | 9506624080 | 950662 | Y | Y | marginal |
| basketball | Basketball | 9506628020 | 950662 | Y | Y | strong |
| guitar | Acoustic guitar | 9202904000 | 920290 | Y | Y | marginal |
| pencils | Colored pencils with metal table knife a | 9609100000 | 960910 | Y | Y | marginal |
| ballpoint_pen | Ballpoint pen tip writing on paper | 9608100000 | 960810 | Y | Y | marginal |
| dog_leash | Striped pet leash | 4201003000 | 420100 | Y | Y | marginal |
| tape_measure | Retractable measuring tape | 9017800000 | 901780 | Y | Y | marginal |

## Known misses
- Vision misreads: desk lamp seen as a display stand, socks as a neck scarf, towel as fabric, food container as a housing.
- Material not visible: wool vs other hair sweater, knitted vs not cap.
- Classification confusions: LED bulb vs LED luminaire, screwdriver vs household tool, office chair swivel vs upholstered seat.

Follow-up questions resolve most marginal cases; the engine assigns a code only when confident.
