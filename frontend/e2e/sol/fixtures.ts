import type { Page } from '@playwright/test';

export const routes = [
  ['dashboard','/'], ['progetti','/progetti'], ['wallet','/wallet'], ['organico','/canone'], ['costi','/analisi-costi'],
  ['riconciliazione','/riconciliazione'], ['anomalie','/anomalie'], ['revisione','/revisione'], ['amministrazione','/amministrazione'],
] as const;
export async function installFixtures(page: Page, mode: 'normal' | 'empty' | 'error' = 'normal', readOnly = false) {
  const writes: { path: string; method: string; body: unknown }[] = [];
  const unhandled: string[] = [];
  const project = { id:'p1',version:1,codice:'IM26001-BMED-PORTALE-CLIENTI',titolo:'Evoluzione della piattaforma digitale e dei servizi al cliente',tipo_contratto:'AQL',budget:'20.0000',consuntivi_diretti:'10',allocato_a_wallet:'0',rimanente_allocato_wallet:'0',consumato_via_wallet:'0',consumato_totale:'10',residuo:'10',data_inizio:'2026-01-01',data_fine_prevista:'2026-12-31',stato_consuntivazione:'ATTIVO',stato_operativo:'IN_CORSO',stato_fatturazione:'DA_FATTURARE',stato_offerta:'ACCETTATA',stato_residuo:'VALIDO',residuo_scade_il:null,residuo_giorni_alla_scadenza:null,residuo_motivo:'Valido',spiegazione_residuo:'Residuo operativo',permissions:{edit:!readOnly,annotate:!readOnly,validate_closure:!readOnly} };
  const projects=[project,{...project,id:'p2',codice:'IM26002-SICUREZZA',titolo:'Sicurezza e compliance',budget:'0',consumato_totale:'2',residuo:'-2',stato_operativo:'DA_VERIFICARE'}];
  const form = { id:'p1',version:1,code:project.codice,title:project.titolo,contract_type:'AQL',aro_code:'',rda_code:'',deliverable:'',client_owner:null,supplier_owner:null,budget_days:'20',start_date:'2026-01-01',planned_end_date:'2026-12-31',actual_closure_date:null,offer_status:'ACCETTATA',timesheet_status:'ATTIVO',billing_status:'DA_FATTURARE',notes:'',reliability:'VERIFICATO',verification_points:[],permissions:{edit:!readOnly,annotate:!readOnly,delete:!readOnly,editable_fields:['title','contract_type','budget_days','planned_end_date','notes','offer_status','timesheet_status','billing_status','reliability','client_owner','supplier_owner','start_date','aro_code','rda_code','deliverable']},readonly:{code:'Identificativo bloccato'} };
  const options={contract_types:[{value:'AQL',label:'AQL'}],offer_statuses:[{value:'ACCETTATA',label:'Accettata'}],timesheet_statuses:[{value:'ATTIVO',label:'Attivo'},{value:'CHIUSO',label:'Chiuso'}],billing_statuses:[{value:'DA_FATTURARE',label:'Da fatturare'}],reliabilities:[{value:'VERIFICATO',label:'Verificato'}],organizations:[],people:[]};
  const balance={anno:2026,allocato:'20',totale_allocato:'20',consumato:'8',consumato_allocazioni:'8',disponibile:'12',disponibile_su_allocazioni:'12',capacita_totale_origini:'30',residuo_wallet_non_allocato:'10',residui_validi_non_allocati:'10',residui_in_scadenza:'3',residui_scaduti:'0',residui_potenziali_da_verificare:'1',budget_residuo_progetti_in_corso:'10',sforamenti_progetti_in_corso:'2',dettaglio_residui:{VALIDO:{giornate:'10',progetti:[]}}};
  const flow={id:'open',version:1,riferimento:null,origine:'IM25-ORIGINE',origine_id:'o1',origine_titolo:'Progetto di provenienza',destinazione:'ACT-2026',destinazione_titolo:'Servizi di analisi architetturale',tipo_attivita:'ATTIVITA',architetto:'Mario Rossi',allocato:'20',consumato:'8',disponibile:'12',residuo_allocazione:'12',residuo_spendibile_origine:'10',validita_origine:'VALIDO',scadenza_origine:'2027-12-31',stato:'APERTA',stato_operativo:'IN_CORSO'};
  const allocation={id:'open',version:1,external_ref:null,allocated_days:'20',initial_allocated_days:'20',consumed_days:'8',available_days:'12',residuo_allocazione:'12',residuo_spendibile_origine:'10',validita_origine:'VALIDO',scadenza_origine:'2027-12-31',status:'APERTA',stato_operativo:'IN_CORSO',notes:'Nota di prova',assignee:null,architetto:'Mario Rossi',source_project_code:'IM25-ORIGINE',source_project_title:'Provenienza',activity_code:'ACT-2026',activity_title:flow.destinazione_titolo,year:2026,funding:[{ordine:1,progetto_origine:'IM25-ORIGINE',anno_provenienza:2025,riservato_iniziale:'20',impegnato:'20',consumato:'8'}]};
  const sub={id:'s1',version:1,office:'EA',title:'Analisi architetturale',reserved_days:'50',start_date:'2026-07-01',end_date:'2026-12-31',remaining_reserved_days:'25',redmine_ref:'300228',quarter_estimate_days:null,forecast_remaining_days:null,notes:'Attivita del semestre',needs_review:false,consuntivato:'25',timesheet_count:1,consuntivi:[{id:'ts1',data:'2026-10-20',giornate:'25',descrizione:'Analisi',utente:'test',origine:'MANUALE'}]};
  const canone={id:'one',version:1,name:'Organico Allargato',semester:'2026-S2',periodicity:'SEMESTRALE',total_days:'100',reserved_days:'50',available_days:'50',target_base_days:'0',target_days_per_week:'0',cap_at_total:true,start_date:'2026-07-01',end_date:'2026-12-31',status:{consuntivato:'25',target_alla_data:'0',delta:'-25',forecast:'50',percentuale_forecast:'50',proiezione:'Sotto-utilizzo previsto',giornate_non_usate_previste:'50'},subactivities: mode==='empty'?[]:[sub]};
  const canoni={default_canone_id:'one',count:1,results:[{id:'one',version:1,semestre:'2026-S2',periodicita:'SEMESTRALE',nome:'Organico Allargato',pianificato:'100',riservato:'50',disponibile:'50',consuntivato:'25',residuo:'75',stato:'IN_CORSO',sottoattivita_count:1}],summary:{pianificato:'100',riservato:'50',disponibile:'50',consuntivato:'25',residuo:'75',sottoattivita:1},filters:{semestri:['2026-S2'],stati:['IN_CORSO'],domini:['EA','TA','SA','CROSS']}};
  const costs={policy:'Costo globale corrente.',kpi:{total_days:'25',total_cost:'10000',daily_person_cost:'400'},by_project:mode==='empty'?[]:[{label:'IM26001 - Evoluzione piattaforma digitale',days:'20',cost:'8000'},{label:'IM26002 - Analisi architetturale',days:'5',cost:'2000'}],by_supplier:[],by_source:[],monthly_trend:[]};
  const recon={riepilogo:{stato:mode==='empty'?'NON_VERIFICABILE':'NON_ALLINEATO',stato_dati:mode==='empty'?'SNAPSHOT_ASSENTE':'DISPONIBILI',righe:2,righe_confrontabili:mode==='empty'?0:2,ok:1,ko:1,assenti_in_ppm:0,delta_totale:mode==='empty'?null:'2',percentuale_allineati:mode==='empty'?null:'50',snapshot_estratto_il:'2026-10-20'},tolleranza:'0.01',results:mode==='empty'?[]:[{codice_progetto:project.codice,nome_progetto:project.titolo,progetto_id:'p1',interno:'20',ppm:'18',delta:'2',esito:'KO',snapshot_estratto_il:'2026-10-20',azione_suggerita:'Verificare le giornate'},{codice_progetto:'IM26002',nome_progetto:'Progetto allineato',progetto_id:'p2',interno:'5',ppm:'5',delta:'0',esito:'OK',snapshot_estratto_il:'2026-10-20',azione_suggerita:''}]};
  const anomaly={id:'a1',external_ref:'CHK-01',codice_regola:'CHK-01',severita:'ALTA',ambito:'PROGETTO',descrizione:'Differenza di consuntivazione da verificare',stato:'APERTA',progetto:project.codice,contesto:{},azione_suggerita:'Controllare il progetto',nota_risoluzione:'',sostituita_da:null};
  const users={roles:[{key:'admin',label:'Amministratore'},{key:'fornitore',label:'Fornitore'}],results:[{id:2,username:'mario',first_name:'Mario',last_name:'Rossi',email:'mario@example.test',is_active:true,is_staff:false,is_superuser:false,roles:['fornitore'],last_login:null,date_joined:'2026-01-01'}]};
  const roles={capabilities:['projects.create','users.manage','data.reset'],reserved:['users.manage'],roles:[{key:'admin',label:'Amministratore',capabilities:['projects.create','users.manage']},{key:'fornitore',label:'Fornitore',capabilities:[]}]};
  const refs=[{id:'ref1',full_name:'Mario Bianchi',email:'mario@example.test',is_active:true,organization_kind:'CLIENT',organization_label:'Cliente (BMED)',project_count:1}];
  let ledger={consuntivi:[{id:'ts1',data:'2026-10-20',giornate:'10',descrizione:'Analisi iniziale',utente:'test'}],wallet:[]};
  await page.route('**/api/v1/**', async route => {
    const request=route.request();const url=new URL(request.url());const p=url.pathname.replace('/api/v1','').replace(/\/$/,'');const method=request.method();let body:Record<string,unknown>={};try{body=request.postDataJSON()??{}}catch{/* multipart */}
    if(p==='/auth/session') return route.fulfill({json:{username:'test',full_name:'Utente di prova',email:'',roles:readOnly?['fornitore']:['admin'],is_admin:!readOnly,can_write:!readOnly,capabilities:readOnly?[]:['projects.create','projects.edit','projects.validate_closure','privileges.manage','users.manage','wallet.edit','accounting.adjust','canone.manage','timesheets.create','data.reset','imports.upload','data.export']}});
    if(method==='GET'&&mode==='error') return route.fulfill({status:503,json:{detail:'Servizio temporaneamente non disponibile',status:503,title:'Errore di prova'}});
    if(method!=='GET') {
      writes.push({path:p,method,body:request.postData()?.includes('Content-Disposition')?request.postData():body});
      if(p.startsWith('/admin/imports/')) return route.fulfill({json:{mode:request.postData()?.includes('\r\ntrue\r\n')?'apply':'dry-run',confirmation_hash:'fixture-hash',batch_id:null,report:{schema_version:'3',esito:'OK',riepilogo:{creati:1,aggiornati:0,scartati:0,errori:0}}}});
      if(p==='/projects') return route.fulfill({status:201,json:{id:'p-new'}});
      if(p==='/projects/p1'&&method==='PATCH'){Object.assign(form,body,{version:form.version+1});return route.fulfill({json:form});}
      if(p==='/projects/p1/ledger'){ledger={...ledger,consuntivi:[...ledger.consuntivi,{id:'ts-new',data:String(body.data),giornate:String(body.giornate),descrizione:String(body.descrizione),utente:'test'}]};return route.fulfill({status:201,json:{id:'ts-new'}});}
      if(p==='/wallet/allocations/open'){Object.assign(allocation,body,{version:allocation.version+1});return route.fulfill({json:allocation});}
      if(p==='/allocations')return route.fulfill({status:201,json:{id:'open'}});
      if(p==='/canoni/one'){Object.assign(canone,body,{version:canone.version+1});return route.fulfill({json:canone});}
      if(p.includes('/canoni/one/subactivities/s1/timesheets'))return route.fulfill({json:canone});
      if(p==='/canoni/one/subactivities/s1'){Object.assign(sub,body,{version:sub.version+1});return route.fulfill({json:canone});}
      if(p==='/canoni/one/subactivities')return route.fulfill({status:201,json:canone});
      if(p==='/canoni')return route.fulfill({status:201,json:canone});
      if(p==='/settings')return route.fulfill({json:{costo_giornata_uomo:String(body.costo_giornata_uomo),politica_costo:'Costo corrente',version:2}});
      if(p.startsWith('/admin/users'))return route.fulfill({json:{...users.results[0],...body}});
      if(p.startsWith('/admin/referents'))return route.fulfill({json:{...refs[0],...body}});
      if(p.startsWith('/admin/roles'))return route.fulfill({json:roles});
      if(p.includes('/confirm-review')||p.startsWith('/anomalies/')||p==='/checks/run'||p==='/auth/logout')return route.fulfill({json:{detail:'Operazione completata'}});
      unhandled.push(method+' '+p);return route.fulfill({status:400,json:{detail:'Fixture non definita'}});
    }
    let data:unknown;
    if(p==='/dashboard')data={generato_il:'2026-10-28',progetti_per_stato:mode==='empty'?[]:[{stato:'ATTIVO',conteggio:2},{stato:'CHIUSO',conteggio:1}],wallet:{anno:2026,allocato:mode==='empty'?'0':'20',consumato:mode==='empty'?'0':'8',disponibile:mode==='empty'?'0':'12'},prossime_fatturazioni:{count:mode==='empty'?0:1,limit:50,results:mode==='empty'?[]:[{id:'m1',progetto_id:'p1',progetto_codice:project.codice,data_pianificata:'2026-10-20',data_fatturazione:'2026-10-20',data_effettiva:null}]}};
    else if(p==='/projects/balances')data={count:mode==='empty'?0:projects.length,results:mode==='empty'?[]:projects};
    else if(p==='/projects/options')data=options;
    else if(p==='/projects/p1')data=form;
    else if(p==='/projects/p1/ledger')data=ledger;
    else if(p.startsWith('/audit/project/'))data={results:[]};
    else if(/\/wallet\/\d+\/balance/.test(p))data=balance;
    else if(p.endsWith('/flow'))data={results:mode==='empty'?[]:[flow]};
    else if(p.endsWith('/assignees'))data={results:[]};
    else if(p==='/wallet/allocations/open')data=allocation;
    else if(p==='/wallet/allocation-options')data={projects:[],activities:[{id:'act1',code:'ACT-2026',title:'Analisi'}],assignees:[{id:'person1',name:'Mario Rossi'}],unallocated_capacity:'10',potential_wallet_capacity:'30'};
    else if(p==='/canoni')data=mode==='empty'?{...canoni,results:[],default_canone_id:null}:canoni;
    else if(p==='/canoni/one')data=canone;
    else if(p==='/cost-analysis')data=costs;
    else if(p==='/reconciliation/latest')data=recon;
    else if(p==='/anomalies')data={results:mode==='empty'?[]:[{...anomaly,stato:url.searchParams.get('stato')||'APERTA'}]};
    else if(p==='/review-queue')data={count:mode==='empty'?0:1,results:mode==='empty'?[]:[{id:'p1',codice:project.codice,titolo:project.titolo,stato_consuntivazione:'ATTIVO',data_chiusura:null,data_fine_prevista:'2026-12-31',motivo_revisione:'Verificare chiusura'}]};
    else if(p==='/admin/imports')data={results:mode==='empty'?[]:[{id:'batch1',kind:'SEED',status:'APPLIED',source_filename:'dati-prova.json',created_at:'2026-10-28'}]};
    else if(p==='/admin/users')data=users;
    else if(p==='/admin/roles/capabilities')data=roles;
    else if(p==='/admin/referents')data={results:refs};
    else if(p==='/settings')data={costo_giornata_uomo:'400',politica_costo:'Costo corrente',version:1};
    else if(p.startsWith('/export/'))return route.fulfill({contentType:'application/octet-stream',headers:{'content-disposition':'attachment; filename="export-test.json"'},body:'{}'});
    else {unhandled.push(method+' '+p);return route.fulfill({status:404,json:{detail:'Fixture non definita'}});}
    return route.fulfill({json:data});
  });
  return { writes, unhandled };
}
