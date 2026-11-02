"""Copy base-glyph pair kerning to accented glyphs."""
from copy import deepcopy

def inherit_kerning(font,mapping):
    # mapping: new glyph name -> base glyph name
    aliases={}
    for new,base in mapping.items():aliases.setdefault(base,[]).append(new)
    order={name:i for i,name in enumerate(font.getGlyphOrder())}
    if 'kern' in font:
        for st in font['kern'].kernTables:
            if not hasattr(st,'kernTable'):continue
            additions={}
            for (left,right),value in list(st.kernTable.items()):
                for l in [left]+aliases.get(left,[]):
                    for r in [right]+aliases.get(right,[]):
                        if (l,r)!=(left,right): additions[(l,r)]=value
            st.kernTable.update(additions)
    if 'GPOS' not in font:return
    gpos=font['GPOS'].table
    if not gpos.FeatureList or not gpos.LookupList:return
    indices={i for r in gpos.FeatureList.FeatureRecord if r.FeatureTag=='kern' for i in r.Feature.LookupListIndex}
    for index in indices:
        lookup=gpos.LookupList.Lookup[index]
        for st in lookup.SubTable:
            pair=st.ExtSubTable if lookup.LookupType==9 and st.ExtensionLookupType==2 else st if lookup.LookupType==2 else None
            if pair is None:continue
            if pair.Format==1:
                for pairset in pair.PairSet:
                    extra=[]
                    for rec in pairset.PairValueRecord:
                        for new in aliases.get(rec.SecondGlyph,[]):
                            clone=deepcopy(rec);clone.SecondGlyph=new;extra.append(clone)
                    pairset.PairValueRecord.extend(extra)
                    pairset.PairValueRecord.sort(key=lambda r:order[r.SecondGlyph])
                    pairset.PairValueCount=len(pairset.PairValueRecord)
                sets=dict(zip(pair.Coverage.glyphs,pair.PairSet))
                for base,news in aliases.items():
                    if base in sets:
                        for new in news:sets[new]=deepcopy(sets[base])
                pair.Coverage.glyphs=sorted(sets,key=order.__getitem__)
                pair.PairSet=[sets[g] for g in pair.Coverage.glyphs];pair.PairSetCount=len(pair.PairSet)
            elif pair.Format==2:
                coverage=set(pair.Coverage.glyphs)
                for base,news in aliases.items():
                    if base in coverage:coverage.update(news)
                    for definition in [pair.ClassDef1,pair.ClassDef2]:
                        if base in definition.classDefs:
                            for new in news:definition.classDefs[new]=definition.classDefs[base]
                pair.Coverage.glyphs=sorted(coverage,key=order.__getitem__)
            else:raise ValueError('Unsupported kerning pair format')
