// Directory entrances keep their own filters; individual documents get a guide.
export function hasDocumentGuide(route) {
 return /^(quests|quest-sources|dialogue-sources|people|regions|places|entities|sources|concepts|factions|sentinels|cosmology|world)\//.test(route)
  || /^(cosmology|sentinels|relationships|events|about)$/.test(route);
}
