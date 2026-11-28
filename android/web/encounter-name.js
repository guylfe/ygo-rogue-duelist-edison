const ACT_LABELS={2:'Act II',3:'Act III'};

export function encounterName(content,opponent,variantAct){
 const name=content.characters[opponent]?.name||'Unknown duelist';
 return ACT_LABELS[variantAct]?name+' ('+ACT_LABELS[variantAct]+')':name;
}

export function routeVariantAct(content,run,opponent){
 if(run?.stage==='duel'&&run.duel?.opponent===opponent)return run.duel.opponent_variant_act;
 if(run?.act&&run.later_opponent_act===run.act&&!run.loop&&!run.encore_active&&
    run.history_mode!=='tag'&&!run.secret_challenge&&!run.fallen_routes?.[opponent]&&
    content.returningOpponents?.[run.act]?.includes(opponent))return run.act;
}

export function routeOpponentName(content,run,opponent){
 return encounterName(content,opponent,routeVariantAct(content,run,opponent));
}
