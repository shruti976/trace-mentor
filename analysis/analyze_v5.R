# Locked V5 manuscript models. No automatic fallback on failure.
args <- commandArgs(TRUE)
if (length(args)!=2) stop('Usage: Rscript analysis/analyze_v5.R EXPORT_DIRECTORY OUTPUT_DIRECTORY')
suppressPackageStartupMessages({library(lme4);library(glmmTMB);library(lmerTest);library(jsonlite)})
lock_path<-file.path(dirname(sub('^--file=','',grep('^--file=',commandArgs(),value=TRUE)[1])),'renv.lock')
lock<-jsonlite::fromJSON(lock_path,simplifyVector=FALSE)
if(as.character(getRversion())!=lock$R$Version)stop('R runtime differs from renv.lock')
for(package in c('lme4','glmmTMB','lmerTest','jsonlite'))if(packageVersion(package)!=package_version(lock$Packages[[package]]$Version))stop(paste('Package differs from lock:',package))
input<-args[1];output<-args[2];dir.create(output,recursive=TRUE,showWarnings=FALSE)
read<-function(name) {path<-file.path(input,paste0(name,'.csv'));if(file.info(path)$size<=2)return(data.frame());read.csv(path,na.strings=c('','NA'),stringsAsFactors=FALSE)}
roster<-read('roster');periods<-read('periods');items<-read('items')
filter_release<-function(x) x[!is.na(x$release_id)&x$release_id=='v5-crossover-2026-09-07'&x$is_test==0&x$is_pilot==0,,drop=FALSE]
roster<-filter_release(roster);periods<-filter_release(periods);items<-filter_release(items)
if(nrow(roster)==0){
  write.csv(data.frame(measure='Randomized',N=0),file.path(output,'participant_flow.csv'),row.names=FALSE)
  jsonlite::write_json(list(status='nonestimable',reason='No eligible randomized participants in this release; no outcome estimates produced.'),file.path(output,'diagnostics.json'),auto_unbox=TRUE,pretty=TRUE)
  writeLines(capture.output(sessionInfo()),file.path(output,'sessionInfo.txt'));quit(status=0)
}
prepare<-function(x){x$condition<-factor(x$condition,levels=c('self_directed','structured'));x$paper_id<-factor(x$paper_id);x$period<-factor(x$period);x$participant_id<-factor(x$participant_id);if('item_id'%in%names(x))x$item_id<-factor(x$item_id);x}
periods<-prepare(periods);items<-prepare(items[!is.na(items$period),,drop=FALSE])
flow<-data.frame(measure=c('Randomized','Complete academic pairs','Completed sessions','H2 count pairs','H3 calibration pairs'),N=c(nrow(roster),sum(roster$complete_pair==1),sum(roster$session_completed==1),0,0))
pair_ids<-function(d,col){splitdata<-split(d,d$participant_id);names(Filter(function(z)nrow(z)==2&&all(!is.na(z[[col]]))&&length(unique(z$condition))==2,splitdata))}
h1<-items[items$complete_pair==1&!is.na(items$correct),,drop=FALSE]
count_periods<-periods
if('source_consultation_complete'%in%names(count_periods))count_periods<-count_periods[count_periods$source_consultation_complete==1,,drop=FALSE]
h2<-count_periods[count_periods$participant_id%in%pair_ids(count_periods,'source_consultation_count'),,drop=FALSE]
h3<-periods[periods$participant_id%in%pair_ids(periods,'absolute_calibration_error'),,drop=FALSE]
flow$N[4:5]<-c(length(unique(h2$participant_id)),length(unique(h3$participant_id)))
write.csv(flow,file.path(output,'participant_flow.csv'),row.names=FALSE)
write.csv(as.data.frame(table(roster$sequence_id,useNA='ifany')),file.path(output,'sequence_counts.csv'),row.names=FALSE)
write.csv(data.frame(field=names(periods),missing=sapply(periods,function(x)sum(is.na(x)))),file.path(output,'missingness.csv'),row.names=FALSE)
write.csv(periods,file.path(output,'period_descriptives_input.csv'),row.names=FALSE)
results<-list();diagnostics<-list()
fit_one<-function(name,d,kind,formula){
  warnings<-character();diag<-list(participants=length(unique(d$participant_id)),rows=nrow(d),family=kind)
  result<-tryCatch(withCallingHandlers({
    if(nrow(d)==0||length(unique(d$condition))<2)stop('Insufficient outcome-complete data')
    response<-all.vars(formula)[1]
    if(length(unique(d[[response]]))<2)stop('Constant outcome; model nonestimable')
    if(qr(model.matrix(lme4::nobars(formula),d))$rank<ncol(model.matrix(lme4::nobars(formula),d)))stop('Rank deficient fixed effects')
    if(kind=='NB2'){
      fit<-glmmTMB(formula,data=d,family=nbinom2(link='log'))
      tab<-summary(fit)$coefficients$cond
      diag$converged<-fit$fit$convergence==0&&isTRUE(fit$sdr$pdHess)
      diag$singular<-any(vapply(VarCorr(fit)$cond,function(v)any(attr(v,'stddev')<1e-4),logical(1)))
      diag$dispersion<-sigma(fit)
      diag$pearson_dispersion<-sum(residuals(fit,type='pearson')^2)/df.residual(fit)
    }else{
      fit<-if(kind=='binomial')lme4::glmer(formula,data=d,family=binomial,control=glmerControl(optimizer='bobyqa',optCtrl=list(maxfun=200000))) else lmerTest::lmer(formula,data=d,REML=TRUE)
      tab<-coef(summary(fit));diag$converged<-is.null(fit@optinfo$conv$lme4$messages)&&fit@optinfo$conv$opt==0
      diag$singular<-lme4::isSingular(fit,tol=1e-4)
      diag$dispersion<-sum(residuals(fit,type='pearson')^2)/df.residual(fit)
    }
    diag$possible_separation<-kind=='binomial'&&(any(abs(fixef(fit))>15)||any(tab[,'Std. Error']>10))
    diagnostics[[name]]<<-diag
    if(!diag$converged||diag$singular||diag$possible_separation)stop('Convergence, singularity, or separation diagnostic failed; no fallback estimate')
    b<-tab['conditionstructured','Estimate'];se<-tab['conditionstructured','Std. Error'];df<-if(kind=='Gaussian')tab['conditionstructured','df'] else Inf
    crit<-if(is.finite(df))qt(.975,df) else qnorm(.975)
    p<-if(is.finite(df))2*pt(-abs(b/se),df) else 2*pnorm(-abs(b/se))
    transform<-if(kind=='Gaussian')identity else exp
    data.frame(hypothesis=name,status='estimable',N=diag$participants,estimate=transform(b),lower=transform(b-crit*se),upper=transform(b+crit*se),p=p,df=df,scale=if(kind=='Gaussian')'absolute-error difference (0–5)' else if(kind=='NB2')'incidence-rate ratio' else 'odds ratio',error=NA_character_)
  },warning=function(w){warnings<<-c(warnings,conditionMessage(w));invokeRestart('muffleWarning')}),error=function(e)data.frame(hypothesis=name,status='nonestimable',N=diag$participants,estimate=NA_real_,lower=NA_real_,upper=NA_real_,p=NA_real_,df=NA_real_,scale=kind,error=conditionMessage(e)))
  diagnostics[[name]]<<-c(diagnostics[[name]] %||% diag,list(warnings=warnings));results[[name]]<<-result
}
`%||%`<-function(x,y)if(is.null(x))y else x
fit_one('H1',h1,'binomial',correct~condition+paper_id+period+(1|participant_id)+(1|item_id))
fit_one('H2',h2,'NB2',source_consultation_count~condition+paper_id+period+(1|participant_id))
fit_one('H3',h3,'Gaussian',absolute_calibration_error~condition+paper_id+period+(1|participant_id))
p1<-items[items$period=='1'&!is.na(items$correct)&!is.na(items$baseline_score),,drop=FALSE]
fit_one('H1_period1',p1,'binomial',correct~condition+paper_id+baseline_score+(1|participant_id)+(1|item_id))
result<-do.call(rbind,results);result$BH_secondary_p<-NA_real_;secondary<-which(result$hypothesis%in%c('H2','H3'));result$BH_secondary_p[secondary]<-p.adjust(result$p[secondary],method='BH',n=2)
write.csv(result,file.path(output,'models.csv'),row.names=FALSE,na='')
write_json(diagnostics,file.path(output,'diagnostics.json'),pretty=TRUE,auto_unbox=TRUE,null='null',na='null')
writeLines(capture.output(sessionInfo()),file.path(output,'R-session.txt'))
writeLines('Outcome-complete populations, not intention-to-treat. No carryover test selects the primary model. No participant learning, transfer or retention claims follow from synthetic checks.',file.path(output,'LIMITATIONS.txt'))
