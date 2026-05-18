# Tietosuojaseloste — BensaVahti

_Päivitetty: 2026-05-18_

## Lyhyesti

**Emme kerää sinusta mitään henkilötietoja.** BensaVahti on julkinen
polttoaineen hintapalvelu, jossa ei ole käyttäjätilejä, kirjautumista,
lomakkeita, evästeitä eikä analytiikka- tai seurantatyökaluja. Ainoat tiedot,
joita liikkeellesi voi kertyä, ovat ne tekniset tiedot, joita
sovelluksen alustat (Railway ja Vercel) keräävät automaattisesti osana
normaalia palvelininfrastruktuuria.

## 1. Rekisterinpitäjä

BensaVahti on harrasteprojekti.
Yhteydenotot: adamallali4@gmail.com

## 2. Mitä tietoja kerätään

### Sovellus itse

- **Ei käyttäjätilejä, ei kirjautumista, ei lomakkeita.** Sovellus ei pyydä
  eikä tallenna nimeä, sähköpostia, sijaintia eikä muita henkilötietoja.
- **Ei evästeitä.** Sovellus ei aseta evästeitä.
- **Ei analytiikkaa eikä seurantaa.** Ei Google Analyticsia, ei
  seurantapikseleitä, ei sormenjälkitunnistusta, ei kolmannen osapuolen
  mainos- tai seurantaskriptejä.
- **Selaimen paikallinen muisti (localStorage):** sovellus tallentaa
  selaimeesi yhden asetuksen — valitsemasi teeman (`theme`: vaalea/tumma).
  Tämä tieto pysyy laitteellasi, sitä ei lähetetä palvelimelle eikä sen
  perusteella voi tunnistaa sinua. Voit poistaa sen tyhjentämällä selaimen
  sivustodatan.

### Alustojen automaattiset lokit

Sovelluksen frontend on Vercelissä ja backend Railwaylla. Nämä alustat
voivat normaalin palvelininfrastruktuurin osana kirjata automaattisesti
teknisiä pyyntötietoja, kuten IP-osoitteen, selaimen user-agentin ja
aikaleimoja (mm. käytön mittaamiseen ja palvelunestohyökkäysten torjuntaan).
Emme käytä näitä alustojen lokeja käyttäjien tunnistamiseen tai
profilointiin. Näiden tietojen käsittelyyn sovelletaan alustojen omia
tietosuojakäytäntöjä:

- Vercel: https://vercel.com/legal/privacy-policy
- Railway: https://railway.app/legal/privacy

## 3. Tietokanta

Backend tallentaa MongoDB Atlas -tietokantaan ainoastaan **julkista
polttoaineen hintadataa** (skrapattu polttoaine.net- ja tankille.fi-sivuilta)
sekä ennusteita ja niiden osumatarkkuutta. Tietokanta ei sisällä
henkilötietoja eikä yksittäisiin käyttäjiin yhdistettävää dataa.

## 4. Push-ilmoitukset (ntfy.sh)

Ilmoitukset julkaistaan ntfy.sh-palvelun julkiseen aiheeseen. Tilaat
ilmoitukset itse omalla laitteellasi ntfy-sovelluksella; BensaVahti ei
tallenna tilaajien tunnisteita eikä tiedä keitä tilaajat ovat. ntfy.sh:n
omaan käsittelyyn sovelletaan ntfy.sh:n tietosuojakäytäntöä
(https://ntfy.sh).

## 5. Kolmansien osapuolten datalähteet

Sovellus hakee taustalla julkista markkinadataa ulkopuolisista lähteistä
(Yahoo Finance: Brent ja EUR/USD; suomalaiset RSS-uutissyötteet;
polttoaine.net; tankille.fi). Yhteydet näihin ovat lähteviä datahakuja —
niiden mukana ei lähetetä sinusta mitään tietoja.

## 6. Tietojen luovutus

Emme myy, vuokraa emmekä luovuta tietoja kolmansille osapuolille — koska
emme kerää henkilötietoja.

## 7. Sinun oikeutesi

Koska sovellus ei kerää henkilötietoja, tunnistettavia tietoja sinusta ei
ole pyydettävänä, oikaistavana tai poistettavana. Selaimeen tallennetun
teema-asetuksen voit poistaa itse tyhjentämällä selaimen sivustodatan.

## 8. Muutokset

Tätä selostetta voidaan päivittää sovelluksen kehittyessä. Muutokset
julkaistaan tällä sivulla ja päiväys yllä päivitetään.

## 9. Yhteydenotot

Tietosuojaa koskevat kysymykset: adamallali4@gmail.com
